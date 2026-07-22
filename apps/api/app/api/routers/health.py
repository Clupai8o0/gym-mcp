"""Liveness/readiness probe with a DB ping (docs/03 DoD)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import health

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Confirm the process is up and the database answers."""
    await health.ping(db)
    return {"status": "ok", "db": "ok"}
