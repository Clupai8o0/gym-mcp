"""Per-request MCP runtime: the authenticated principal + the DB-session source.

MCP tools run inside the mounted Streamable-HTTP ASGI app, not through FastAPI's
dependency injection, so they can't take ``db``/``current_user`` as parameters. Instead
the auth wrapper (:mod:`app.mcp.asgi`) resolves the bearer token once and binds the
resulting principal here; tools read it back via :func:`current_user_id` and open their own
session via :func:`open_session`. Both are indirections a test can swap — the principal via
:func:`bind_principal`, the session via :func:`set_session_factory` — so tools are callable
directly against a rolled-back test session (the MCP↔REST contract tests do exactly that).

This module is a pure runtime shim: it never touches the DB itself (the architecture guard
in ``tests/test_architecture.py`` enforces that for everything under ``app/mcp``).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractAsyncContextManager, contextmanager
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.db import session_scope
from app.services.oauth import TokenPrincipal

# The scope vocabulary the AS issues (services/oauth.SUPPORTED_SCOPES). Reads need the read
# scope (enforced at the transport by the auth wrapper); writes additionally need write.
READ_SCOPE = "workouts.read"
WRITE_SCOPE = "workouts.write"

_principal: ContextVar[TokenPrincipal | None] = ContextVar("mcp_principal", default=None)

# Indirection so tests can point tool + auth DB access at the rolled-back test session.
SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
_session_factory: SessionFactory = session_scope


def current_principal() -> TokenPrincipal:
    """The bearer principal bound for this request, or raise if unauthenticated."""
    principal = _principal.get()
    if principal is None:  # the auth wrapper binds before any tool runs; a miss is a bug
        raise errors.unauthorized("No authenticated MCP principal in context")
    return principal


def current_user_id() -> uuid.UUID:
    """The ``user_id`` the current bearer token authorizes."""
    return current_principal().user_id


def require_scope(scope: str) -> None:
    """Raise ``forbidden`` unless the current principal was granted ``scope``."""
    if scope not in current_principal().scopes:
        raise errors.forbidden(f"This action requires the '{scope}' scope")


@contextmanager
def bind_principal(principal: TokenPrincipal) -> Iterator[None]:
    """Bind ``principal`` as the current MCP identity for the duration of the block."""
    token = _principal.set(principal)
    try:
        yield
    finally:
        _principal.reset(token)


def open_session() -> AbstractAsyncContextManager[AsyncSession]:
    """Open a DB session context for a tool/auth call (commit on success, rollback on error)."""
    return _session_factory()


def set_session_factory(factory: SessionFactory) -> None:
    """Override the session source (tests point this at the rolled-back test session)."""
    global _session_factory
    _session_factory = factory


def reset_session_factory() -> None:
    """Restore the default session source."""
    global _session_factory
    _session_factory = session_scope
