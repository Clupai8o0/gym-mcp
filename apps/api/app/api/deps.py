"""FastAPI dependencies: DB session, current user, and pagination.

These are the only place request/session state is read. They resolve values and hand
them to services — they contain no domain logic or ad-hoc DB queries themselves.

``current_user`` (Phase 3) resolves identity from **either** an OAuth **bearer** token
(MCP/programmatic — audience-bound to the MCP resource) **or** the signed web **session**
cookie (browser). Cookie-authenticated *mutations* additionally require the ``X-Tempo-Client``
header: a custom header forces a CORS preflight only our web origin passes, so a cross-site
page cannot forge an authenticated write (docs/05 CSRF).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import session as auth_session
from app.core import errors
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.oauth import resource
from app.services import oauth as oauth_service

# Header carried by browser calls (CORS-exposed); the CSRF signal for cookie-authed mutations.
CLIENT_HEADER = "X-Tempo-Client"

# The account owner (web session) holds full scopes; a bearer token carries only what it was
# granted. Session scope strings use the same dot form the OAuth metadata advertises.
SESSION_SCOPES = frozenset({"workouts.read", "workouts.write"})
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session; commit on success, roll back on error."""
    maker = get_sessionmaker()
    session = maker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated principal for a request."""

    user_id: uuid.UUID
    scopes: frozenset[str]
    via: str  # 'session' (cookie) | 'bearer' (OAuth token)


async def current_user(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Resolve the caller from a bearer token or the web session cookie; 401 if neither.

    Bearer takes precedence (it is unambiguous and used by MCP/programmatic clients). A bearer
    token must be valid, unexpired, unrevoked, and audience-bound to the MCP resource.
    """
    token = resource.extract_bearer_token(request)
    if token is not None:
        principal = await oauth_service.resolve_access_token(
            db, token=token, required_resource=get_settings().mcp_resource
        )
        if principal is None:
            raise errors.unauthorized("Invalid or expired access token")
        return CurrentUser(user_id=principal.user_id, scopes=principal.scopes, via="bearer")

    info = auth_session.read_session(request)
    if info is not None:
        if request.method in _UNSAFE_METHODS and request.headers.get(CLIENT_HEADER) is None:
            raise errors.forbidden("Missing X-Tempo-Client header for a cookie-authenticated write")
        if auth_session.should_renew(info):  # sliding-session renewal (best-effort)
            auth_session.set_session_cookie(
                response, auth_session.issue_session_token(info.user_id)
            )
        return CurrentUser(user_id=info.user_id, scopes=SESSION_SCOPES, via="session")

    raise errors.unauthorized("Authentication required")


@dataclass(frozen=True)
class Pagination:
    limit: int
    offset: int


def pagination(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Pagination:
    """Standard ``?limit=&offset=`` (default 50, max 100)."""
    return Pagination(limit=limit, offset=offset)
