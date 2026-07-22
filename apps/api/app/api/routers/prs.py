"""Personal-record endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, get_db
from app.schemas.prs import PrHistoryOut, PrListOut, PrOut
from app.schemas.sets import SetOut
from app.services import prs

router = APIRouter(prefix="/api/prs", tags=["prs"])


@router.get("", response_model=PrListOut)
async def list_prs(
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    exercise_id: uuid.UUID | None = Query(default=None),
) -> PrListOut:
    rows = await prs.list_prs(db, user_id=cu.user_id, exercise_id=exercise_id)
    return PrListOut(items=[PrOut.from_pair(row) for row in rows])


@router.get("/history", response_model=PrHistoryOut)
async def pr_history(
    exercise_id: uuid.UUID = Query(...),
    pr_type: str = Query(...),
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PrHistoryOut:
    rows = await prs.history(db, user_id=cu.user_id, exercise_id=exercise_id, pr_type=pr_type)
    return PrHistoryOut(
        exercise_id=exercise_id,
        pr_type=pr_type,
        items=[SetOut.model_validate(row) for row in rows],
    )
