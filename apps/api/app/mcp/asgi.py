"""OAuth guard + mount for the MCP endpoint (docs/04 auth, docs/05 B5).

``/mcp`` is an OAuth 2.0 protected resource. This wraps the Streamable-HTTP ASGI app with a
bearer check that reuses the **same** ``resolve_access_token`` service REST's ``current_user``
uses — one auth path, no second implementation. Unauthenticated/expired → 401 with the
RFC 9728 ``WWW-Authenticate`` PRM pointer; a token lacking the baseline read scope → 403; a
valid token is bound as the request principal (:mod:`app.mcp.runtime`) and the request is
handed to the MCP app, where each tool runs scoped to that user.

The endpoint is attached as a Starlette ``Route`` (not a ``Mount``) so ``/mcp`` resolves at the
exact path with no trailing-slash redirect — claude.ai POSTs to ``…/mcp`` verbatim.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from app.core.config import get_settings
from app.mcp import runtime, server
from app.mcp.runtime import READ_SCOPE
from app.oauth import resource
from app.services import oauth as oauth_service


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

        with runtime.bind_principal(principal):
            await server.ensure_session_manager().handle_request(scope, receive, send)


def build_mcp_route() -> Route:
    """The ``/mcp`` route: the OAuth-guarded Streamable-HTTP app at the exact path."""
    return Route("/mcp", endpoint=MCPAuthApp())


@asynccontextmanager
async def mcp_lifespan(_app: Starlette) -> AsyncIterator[None]:
    """Run the Streamable-HTTP session manager for the app's lifetime.

    Mounted MCP apps don't get their lifespan run by the parent, so the parent app must drive
    the session manager itself (its task group backs every request). Wired as the FastAPI
    ``lifespan`` in :func:`app.main.create_app`.
    """
    async with server.ensure_session_manager().run():
        yield
