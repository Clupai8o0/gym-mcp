"""Set edit/delete endpoints (logging a set lives under its session)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, get_db
from app.schemas.sets import LoggedSetOut, SetOut, SetUpdate
from app.services import sets

router = APIRouter(prefix="/api/sets", tags=["sets"])


@router.patch("/{set_id}", response_model=LoggedSetOut)
async def update_set(
    set_id: uuid.UUID,
    payload: SetUpdate,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> LoggedSetOut:
    logged = await sets.update_set(
        db,
        user_id=cu.user_id,
        set_id=set_id,
        changes=payload.model_dump(exclude_unset=True),
    )
    return LoggedSetOut.from_logged(logged)


@router.delete("/{set_id}", response_model=SetOut)
async def delete_set(
    set_id: uuid.UUID,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SetOut:
    """Soft-delete a set and recompute its exercise's records.

    Returns the removed row rather than 204 so the caller has the id to `restore` with, and can
    see it really was this set. The record it may have held falls back to the next best.
    """
    removed = await sets.delete_set(db, user_id=cu.user_id, set_id=set_id)
    return SetOut.model_validate(removed)
