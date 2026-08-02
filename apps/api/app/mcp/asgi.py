"""OAuth guard + mount for the MCP endpoint (docs/04 auth, docs/05 B5).

``/mcp`` is an OAuth 2.0 protected resource. This wraps the Streamable-HTTP ASGI app with a
bearer check that reuses the **same** ``resolve_access_token`` service REST's ``current_user``
uses — one auth path, no second implementation. Unauthenticated/expired → 401 with the
RFC 9728 ``WWW-Authenticate`` PRM pointer; a token lacking the baseline read scope → 403; a
valid token is bound as the request principal (:mod:`app.mcp.runtime`) and the request is
handed to the MCP app, where each tool runs scoped to that user.

The endpoint is attached as a Starlette ``Route`` (not a ``Mount``) so ``/mcp`` resolves at the
exact path with no trailing-slash redirect — claude.ai POSTs to ``…/mcp`` verbatim.

**Nothing here imports the MCP SDK at module scope** (docs/13 S1). Importing
:mod:`app.mcp.server` costs ~112 ms — the single largest item in ``import app.main`` — and no
REST request ever needs it. The import, and the session manager it builds, are deferred to the
first request that actually addresses ``/mcp``; see :class:`_LazyTransport`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from app.core.config import get_settings
from app.mcp import runtime
from app.mcp.runtime import READ_SCOPE
from app.oauth import resource
from app.services import oauth as oauth_service


class _LazyTransport:
    """Owns the Streamable-HTTP session manager's lifetime, started on first ``/mcp`` use.

    The manager's ``run()`` is an ``anyio`` task group, and a task group must be entered and
    exited by the **same task** — so it cannot simply be opened from whichever request happens
    to arrive first and closed at shutdown. Instead the lifespan spawns one worker that parks on
    an event; the first ``/mcp`` request sets it, the worker enters ``run()`` and stays there
    until shutdown, then exits it cleanly. Request tasks only ever call ``handle_request``,
    exactly as before.

    A REST-only process therefore never imports the SDK at all. The first ``/mcp`` request pays
    the import once; every subsequent one waits on an already-set event.
    """

    def __init__(self) -> None:
        self._wanted: asyncio.Event | None = None
        self._ready: asyncio.Event | None = None
        self._failure: BaseException | None = None

    @asynccontextmanager
    async def lifespan(self) -> AsyncIterator[None]:
        wanted, ready, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self._wanted, self._ready, self._failure = wanted, ready, None

        async def _worker() -> None:
            await wanted.wait()
            if stop.is_set():  # shut down before anyone asked for /mcp — never import the SDK
                ready.set()
                return
            try:
                from app.mcp import server

                async with server.ensure_session_manager().run():
                    ready.set()
                    await stop.wait()
            except BaseException as exc:  # noqa: BLE001 — re-raised below, after unblocking
                # Record it *and* release the waiter: a failed start must surface at the
                # request that triggered it, not hang it forever.
                self._failure = exc
                ready.set()
                raise

        worker = asyncio.create_task(_worker())
        try:
            yield
        finally:
            stop.set()
            wanted.set()  # unpark the worker even if /mcp was never touched, so it can finish
            self._wanted = self._ready = None
            await asyncio.gather(worker, return_exceptions=True)

    async def ensure_running(self) -> None:
        """Block until the session manager is up, starting it on the first call.

        When no lifespan of ours is running, the process is driving the manager itself — the
        test harness does, since ``ASGITransport`` runs no lifespan — so there is nothing to
        start here. If nobody is, ``handle_request`` raises its own explicit "task group is not
        initialized" error, which is a clearer failure than anything this could invent.
        """
        wanted, ready = self._wanted, self._ready
        if wanted is None or ready is None:
            return
        wanted.set()
        await ready.wait()
        if self._failure is not None:
            raise self._failure


_transport = _LazyTransport()


class MCPAuthApp:
    """ASGI app: enforce the OAuth bearer, then delegate to the MCP session manager."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # pragma: no cover — Route only dispatches http
            return

        request = Request(scope, receive)
        token = resource.extract_bearer_token(request)
        if token is None:  # anonymous — answer with the PRM pointer without touching the DB
            await resource.unauthorized_response()(scope, receive, send)
            return

        async with runtime.open_session() as db:
            principal = await oauth_service.resolve_access_token(
                db, token=token, required_resource=get_settings().mcp_resource
            )

        if principal is None:
            await resource.unauthorized_response()(scope, receive, send)
            return
        if READ_SCOPE not in principal.scopes:
            await resource.insufficient_scope_response(READ_SCOPE)(scope, receive, send)
            return

        # Only an authenticated, in-scope request is worth booting the MCP runtime for. An
        # unauthenticated probe — which is most of what an public endpoint receives — is
        # answered above without ever importing the SDK.
        await _transport.ensure_running()

        from app.mcp import server

        with runtime.bind_principal(principal):
            await server.ensure_session_manager().handle_request(scope, receive, send)


def build_mcp_route() -> Route:
    """The ``/mcp`` route: the OAuth-guarded Streamable-HTTP app at the exact path."""
    return Route("/mcp", endpoint=MCPAuthApp())


@asynccontextmanager
async def mcp_lifespan(_app: Starlette) -> AsyncIterator[None]:
    """Hold the Streamable-HTTP session manager for the app's lifetime — lazily.

    Mounted MCP apps don't get their lifespan run by the parent, so the parent app must drive
    the session manager itself (its task group backs every request). Wired as the FastAPI
    ``lifespan`` in :func:`app.main.create_app`. This starts a parked worker rather than the
    manager, so boot stays MCP-free; see :class:`_LazyTransport`.
    """
    async with _transport.lifespan():
        yield
