"""FastAPI dependencies: DB session, current user, and pagination.

These are the only place request/session state is read. They resolve values and hand
them to services — they contain no domain logic or ad-hoc DB queries themselves.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker
from app.services import users

# Scopes the stubbed dev user carries. Phase 3 derives real scopes from the token.
DEV_SCOPES = frozenset({"profile:read", "workouts:read", "workouts:write"})


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
    via: str  # 'stub' now; 'session' | 'bearer' from Phase 3


async def current_user(db: AsyncSession = Depends(get_db)) -> CurrentUser:
    """Phase 2 stub: resolve to the fixed dev user (auto-provisioned).

    Replaced in Phase 3 by real resolution from the web-session cookie **or** an OAuth
    bearer token. Keeping the interface (``CurrentUser``) stable means routers don't change.
    """
    user = await users.ensure_dev_user(db)
    return CurrentUser(user_id=user.id, scopes=DEV_SCOPES, via="stub")


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
