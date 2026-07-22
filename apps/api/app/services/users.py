"""User lookups + the Phase 2 development-user stub.

Until real Google OIDC login lands (Phase 3), ``current_user`` resolves to a single
fixed development account. :func:`ensure_dev_user` provisions it idempotently so that
FK-bearing writes (sessions, sets) work against a real ``users`` row. Phase 3 replaces
the stub with session/bearer resolution and removes this shortcut.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.models import User

# Sentinel identity for the stubbed dev user (never a real Google account).
DEV_EMAIL = "dev@tempo.local"
DEV_GOOGLE_SUB = "dev-stub-user"
DEV_NAME = "Dev User"


async def ensure_dev_user(db: AsyncSession) -> User:
    """Return the singleton dev user, creating it on first use (race-safe upsert)."""
    await db.execute(
        pg_insert(User)
        .values(email=DEV_EMAIL, google_sub=DEV_GOOGLE_SUB, name=DEV_NAME)
        .on_conflict_do_update(
            index_elements=[User.google_sub],
            set_={"last_login_at": func.now()},
        )
    )
    await db.flush()
    return (await db.execute(select(User).where(User.google_sub == DEV_GOOGLE_SUB))).scalar_one()


async def get(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Fetch a user by id, or raise ``not_found``."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise errors.not_found("User not found")
    return user
