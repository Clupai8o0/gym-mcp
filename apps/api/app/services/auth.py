"""Identity service — resolve a Google-authenticated user to a ``users`` row (docs/05 A).

Framework-free (``db`` in, model out): the Google OIDC *protocol* (building the auth URL,
exchanging the code, verifying the ID token) lives in the ``app/auth`` adapter; this module
is only the DB side — turn a verified Google subject into a Tempo user, idempotently.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def upsert_google_user(
    db: AsyncSession,
    *,
    google_sub: str,
    email: str,
    name: str | None = None,
    avatar_url: str | None = None,
) -> User:
    """Create or update the user identified by ``google_sub``; stamp ``last_login_at``.

    Keyed on the stable Google subject id (never the email, which can change). Race-safe:
    two concurrent logins converge via ``ON CONFLICT`` rather than raising a duplicate.
    """
    await db.execute(
        pg_insert(User)
        .values(google_sub=google_sub, email=email, name=name, avatar_url=avatar_url)
        .on_conflict_do_update(
            index_elements=[User.google_sub],
            set_={
                "email": email,
                "name": name,
                "avatar_url": avatar_url,
                "last_login_at": func.now(),
            },
        )
    )
    await db.flush()
    return (await db.execute(select(User).where(User.google_sub == google_sub))).scalar_one()
