"""User lookups + a development-account helper.

Real request auth is Google OIDC (session cookie) or an OAuth bearer token as of Phase 3 —
``api.deps.current_user`` no longer uses the stub. :func:`ensure_dev_user` survives only as a
**test/local-dev convenience** (idempotently provisioning a real ``users`` row so FK-bearing
writes work); it is not wired into any production code path.
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
    """Return the singleton dev/test user, creating it on first use (race-safe upsert)."""
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
