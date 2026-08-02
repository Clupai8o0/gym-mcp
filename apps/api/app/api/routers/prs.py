"""Personal-record endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, get_db
from app.schemas.prs import (
    PrCreate,
    PrDeleteOut,
    PrHistoryItem,
    PrHistoryOut,
    PrListOut,
    PrOut,
    PrUpdate,
)
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


@router.post("", response_model=PrOut, status_code=201)
async def log_pr(
    payload: PrCreate,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PrOut:
    """Record a PR by hand — the REST twin of the MCP ``log_pr`` tool.

    For records a logged set cannot express: an estimated 1RM, a hold timed outside a session, or
    a PR migrated from another app. Overwrites whatever is stored for this exercise + metric.
    """
    row = await prs.log_manual_pr(
        db,
        user_id=cu.user_id,
        exercise_id=payload.exercise_id,
        pr_type=payload.pr_type,
        value=payload.value,
        achieved_at=payload.achieved_at,
        session_id=payload.session_id,
        notes=payload.notes,
        client_key=payload.client_key,
    )
    return PrOut.from_pair(row)


@router.patch("/{pr_id}", response_model=PrOut)
async def update_pr(
    pr_id: uuid.UUID,
    payload: PrUpdate,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PrOut:
    """Correct a hand-entered record in place, without the delete-and-reinsert dance."""
    row = await prs.update_pr(
        db,
        user_id=cu.user_id,
        pr_id=pr_id,
        value=payload.value,
        achieved_at=payload.achieved_at,
        notes=payload.notes,
        clear_notes=payload.clear_notes,
    )
    return PrOut.from_pair(row)


@router.delete("/{pr_id}", response_model=PrDeleteOut)
async def delete_pr(
    pr_id: uuid.UUID,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PrDeleteOut:
    """Withdraw a hand-entered record; the next best becomes current rather than leaving a gap."""
    standing = await prs.delete_pr(db, user_id=cu.user_id, pr_id=pr_id)
    return PrDeleteOut(standing=PrOut.from_pair(standing) if standing else None)


@router.delete("/history/{entry_id}", response_model=PrHistoryItem)
async def delete_pr_history_entry(
    entry_id: uuid.UUID,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PrHistoryItem:
    """Remove one chronology entry, then rebuild the record from what is left."""
    entry = await prs.delete_history_entry(db, user_id=cu.user_id, entry_id=entry_id)
    return PrHistoryItem.from_row(entry)


@router.get("/history", response_model=PrHistoryOut)
async def pr_history(
    exercise_id: uuid.UUID = Query(...),
    pr_type: str = Query(...),
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    include_deleted: bool = Query(default=False),
    include_uncounted: bool = Query(default=False),
) -> PrHistoryOut:
    rows = await prs.history(
        db,
        user_id=cu.user_id,
        exercise_id=exercise_id,
        pr_type=pr_type,
        include_deleted=include_deleted,
        include_uncounted=include_uncounted,
    )
    return PrHistoryOut(
        exercise_id=exercise_id,
        pr_type=pr_type,
        items=[PrHistoryItem.from_row(row) for row in rows],
    )
