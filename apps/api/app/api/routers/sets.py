"""Set edit/delete endpoints (logging a set lives under its session)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, get_db
from app.schemas.sets import LoggedSetOut, SetUpdate
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


@router.delete("/{set_id}", status_code=204)
async def delete_set(
    set_id: uuid.UUID,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await sets.delete_set(db, user_id=cu.user_id, set_id=set_id)
    return Response(status_code=204)
