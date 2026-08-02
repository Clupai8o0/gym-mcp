"""Repair endpoints: PR recalculation, integrity verification, restore, purge.

The REST half of the correction tooling (docs/04). Every one of these has an MCP twin calling the
same service — a chat client is the likeliest place a correction is made from, and the guardrail
is that neither surface can grow behaviour the other lacks.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, get_db
from app.schemas.corrections import (
    IntegrityOut,
    PurgeIn,
    PurgeOut,
    RecalculationOut,
    RestoreIn,
    RestoreOut,
)
from app.services import corrections, integrity

router = APIRouter(prefix="/api/corrections", tags=["corrections"])


@router.post("/recalculate-prs", response_model=RecalculationOut)
async def recalculate_prs(
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    exercise_id: uuid.UUID | None = Query(default=None),
    pr_type: str | None = Query(default=None),
    dry_run: bool = Query(default=False),
) -> RecalculationOut:
    """Rebuild personal records and their chronology from the live sets + hand-entered claims."""
    report = await integrity.recalculate(
        db, user_id=cu.user_id, exercise_id=exercise_id, pr_type=pr_type, dry_run=dry_run
    )
    return RecalculationOut.from_report(report, dry_run=dry_run)


@router.get("/verify-prs", response_model=IntegrityOut)
async def verify_prs(
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    exercise_id: uuid.UUID | None = Query(default=None),
) -> IntegrityOut:
    """Read-only: report any exercise whose record tables disagree with themselves."""
    return IntegrityOut.from_report(
        await integrity.verify(db, user_id=cu.user_id, exercise_id=exercise_id)
    )


@router.post("/restore", response_model=RestoreOut)
async def restore(
    payload: RestoreIn,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> RestoreOut:
    """Undo a soft delete and rebuild whatever records depended on the row being gone."""
    return RestoreOut.from_result(
        await corrections.restore(
            db,
            user_id=cu.user_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
        )
    )


@router.post("/purge", response_model=PurgeOut)
async def purge(
    payload: PurgeIn,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PurgeOut:
    """Hard-delete rows soft-deleted longer ago than ``older_than_days``. Irreversible."""
    return PurgeOut.from_report(
        await corrections.purge(
            db,
            user_id=cu.user_id,
            older_than_days=payload.older_than_days,
            dry_run=payload.dry_run,
        )
    )
