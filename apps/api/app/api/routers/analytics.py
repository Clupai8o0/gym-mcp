"""Analytics endpoints (volume, frequency)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, get_db
from app.schemas.analytics import FrequencyItem, FrequencyOut, VolumeItem, VolumeOut
from app.services import analytics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/volume", response_model=VolumeOut)
async def volume(
    date_from: datetime = Query(alias="from"),
    date_to: datetime = Query(alias="to"),
    exercise_id: uuid.UUID | None = Query(default=None),
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> VolumeOut:
    buckets = await analytics.volume(
        db, user_id=cu.user_id, date_from=date_from, date_to=date_to, exercise_id=exercise_id
    )
    return VolumeOut(
        date_from=date_from,
        date_to=date_to,
        items=[VolumeItem.model_validate(b) for b in buckets],
    )


@router.get("/frequency", response_model=FrequencyOut)
async def frequency(
    weeks: int = Query(default=8, ge=1, le=52),
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> FrequencyOut:
    counts = await analytics.frequency(db, user_id=cu.user_id, weeks=weeks)
    return FrequencyOut(
        weeks=weeks,
        items=[FrequencyItem.model_validate(c) for c in counts],
    )
