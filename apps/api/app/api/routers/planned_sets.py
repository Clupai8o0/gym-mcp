"""Planned-set edit/delete/complete endpoints (writing a prescription lives under its session)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, get_db
from app.schemas.plans import (
    CompletedPlannedSetOut,
    PlannedSetComplete,
    PlannedSetOut,
    PlannedSetUpdate,
)
from app.services import plans

router = APIRouter(prefix="/api/planned-sets", tags=["planned-sets"])


@router.patch("/{planned_set_id}", response_model=PlannedSetOut)
async def update_planned_set(
    planned_set_id: uuid.UUID,
    payload: PlannedSetUpdate,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PlannedSetOut:
    """Correct one line of a prescription. Never touches what was logged against it."""
    changes = payload.model_dump(exclude_unset=True)
    clear_notes = bool(changes.pop("clear_notes", False))
    planned = await plans.update_planned_set(
        db,
        user_id=cu.user_id,
        planned_set_id=planned_set_id,
        changes=changes,
        clear_notes=clear_notes,
    )
    return PlannedSetOut.model_validate(planned)


@router.delete("/{planned_set_id}", response_model=PlannedSetOut)
async def delete_planned_set(
    planned_set_id: uuid.UUID,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PlannedSetOut:
    """Soft-delete one prescribed line.

    Returns the removed row rather than 204, for the same reason `DELETE /api/sets/{id}` does: the
    caller gets the id to `restore` with. A set already logged against the line stays exactly where
    it is and simply becomes off-plan work.
    """
    removed = await plans.delete_planned_set(db, user_id=cu.user_id, planned_set_id=planned_set_id)
    return PlannedSetOut.model_validate(removed)


@router.post("/{planned_set_id}/complete", response_model=CompletedPlannedSetOut, status_code=201)
async def complete_planned_set(
    planned_set_id: uuid.UUID,
    payload: PlannedSetComplete,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> CompletedPlannedSetOut:
    """Log what was actually done against a prescribed line; normal PR detection applies."""
    completion = await plans.complete(
        db,
        user_id=cu.user_id,
        planned_set_id=planned_set_id,
        **payload.model_dump(),
    )
    return CompletedPlannedSetOut.from_completion(completion)
