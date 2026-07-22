"""Liveness/readiness helper: a trivial DB round-trip."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ping(db: AsyncSession) -> None:
    """Execute ``SELECT 1`` to confirm the DB connection is live; raises on failure."""
    await db.execute(text("SELECT 1"))
