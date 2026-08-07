"""Workout-session endpoints, including logging a set into a session."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, Pagination, current_user, get_db, pagination
from app.schemas.plans import (
    PlannedSessionCreate,
    PlannedSessionOut,
    PlannedSetsCreate,
    SessionProgressOut,
)
from app.schemas.sessions import (
    ActiveSessionOut,
    FinishedSessionOut,
    SessionCreate,
    SessionDeleteOut,
    SessionDetailOut,
    SessionListOut,
    SessionOut,
    SessionUpdate,
    SessionWithSetsCreate,
    SessionWithSetsOut,
)
from app.schemas.sets import LoggedSetOut, LoggedSetsOut, SetBulkCreate, SetCreate
from app.services import plans, sessions, sets

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=SessionListOut)
async def list_sessions(
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    page: Pagination = Depends(pagination),
    type: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
) -> SessionListOut:
    rows, total = await sessions.list_sessions(
        db,
        user_id=cu.user_id,
        type=type,
        date_from=date_from,
        date_to=date_to,
        limit=page.limit,
        offset=page.offset,
    )
    return SessionListOut(
        items=[SessionOut.model_validate(row) for row in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(
    payload: SessionCreate,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    session = await sessions.create(db, user_id=cu.user_id, **payload.model_dump())
    return SessionOut.model_validate(session)


# Declared before "/{session_id}" so the literal wins — otherwise "active" is parsed as a UUID.
@router.get("/active", response_model=ActiveSessionOut)
async def get_active_session(
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ActiveSessionOut:
    """The in-progress session, or `null`. May finish sessions abandoned >12 h (see the service)."""
    active = await sessions.get_active_session(db, user_id=cu.user_id)
    if active is None:
        return ActiveSessionOut(session=None, set_count=0)
    return ActiveSessionOut(
        session=SessionOut.model_validate(active.session),
        set_count=active.set_count,
        planned_total=active.planned_total,
        completed_count=active.completed_count,
    )


# Literal paths before "/{session_id}", for the same reason "/active" is above it.
@router.post("/with-sets", response_model=SessionWithSetsOut, status_code=201)
async def create_session_with_sets(
    payload: SessionWithSetsCreate,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionWithSetsOut:
    """Create a session and its sets in one transaction — all or nothing."""
    body = payload.model_dump()
    drafts = body.pop("sets")
    session = await sessions.create(db, user_id=cu.user_id, **body)
    logged = await sets.log_sets(
        db,
        user_id=cu.user_id,
        session_id=session.id,
        drafts=[sets.SetDraft(**draft) for draft in drafts],
    )
    return SessionWithSetsOut(
        session=SessionOut.model_validate(session),
        sets=[LoggedSetOut.from_logged(row) for row in logged],
    )


@router.post("/planned", response_model=PlannedSessionOut, status_code=201)
async def plan_session(
    payload: PlannedSessionCreate,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PlannedSessionOut:
    """Create a session and its prescription in one transaction — a workout not yet performed."""
    body = payload.model_dump()
    drafts = body.pop("planned_sets")
    plan = await plans.plan_session(
        db,
        user_id=cu.user_id,
        drafts=[plans.PlannedSetDraft(**draft) for draft in drafts],
        **body,
    )
    return PlannedSessionOut.from_plan(plan)


@router.get("/{session_id}/planned", response_model=PlannedSessionOut)
async def get_planned_session(
    session_id: uuid.UUID,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PlannedSessionOut:
    """A session's prescription in performance order, each line with its completion state."""
    plan = await plans.get_plan(db, user_id=cu.user_id, session_id=session_id)
    return PlannedSessionOut.from_plan(plan)


@router.post("/{session_id}/planned", response_model=PlannedSessionOut, status_code=201)
async def add_planned_sets(
    session_id: uuid.UUID,
    payload: PlannedSetsCreate,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> PlannedSessionOut:
    """Append lines to an existing session's prescription, transactionally."""
    await plans.add_planned_sets(
        db,
        user_id=cu.user_id,
        session_id=session_id,
        drafts=[plans.PlannedSetDraft(**draft.model_dump()) for draft in payload.planned_sets],
    )
    plan = await plans.get_plan(db, user_id=cu.user_id, session_id=session_id)
    return PlannedSessionOut.from_plan(plan)


@router.get("/{session_id}/progress", response_model=SessionProgressOut)
async def session_progress(
    session_id: uuid.UUID,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionProgressOut:
    """Planned vs completed for one session, what is left, and what is next."""
    report = await plans.progress(db, user_id=cu.user_id, session_id=session_id)
    return SessionProgressOut.from_progress(report)


@router.get("/{session_id}", response_model=SessionDetailOut)
async def get_session(
    session_id: uuid.UUID,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionDetailOut:
    detail = await sessions.get(db, user_id=cu.user_id, session_id=session_id)
    return SessionDetailOut.from_detail(detail)


@router.patch("/{session_id}", response_model=SessionOut)
async def update_session(
    session_id: uuid.UUID,
    payload: SessionUpdate,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    changes = payload.model_dump(exclude_unset=True)
    clear_notes = bool(changes.pop("clear_notes", False))
    session = await sessions.update(
        db,
        user_id=cu.user_id,
        session_id=session_id,
        changes=changes,
        clear_notes=clear_notes,
    )
    return SessionOut.model_validate(session)


@router.delete("/{session_id}", response_model=SessionDeleteOut)
async def delete_session(
    session_id: uuid.UUID,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    cascade: bool = Query(default=True),
    dry_run: bool = Query(default=False),
) -> SessionDeleteOut:
    """Soft-delete a session and (with `cascade`) its sets, recalculating every PR affected."""
    result = await sessions.delete(
        db, user_id=cu.user_id, session_id=session_id, cascade=cascade, dry_run=dry_run
    )
    return SessionDeleteOut(
        session=SessionOut.model_validate(result.session),
        set_count=result.set_count,
        exercises_recalculated=result.exercises_recalculated,
        dry_run=result.dry_run,
        planned_count=result.planned_count,
    )


@router.post("/{session_id}/finish", response_model=FinishedSessionOut)
async def finish_session(
    session_id: uuid.UUID,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> FinishedSessionOut:
    """Close a session, store its duration, and report adherence. Idempotent."""
    finished = await sessions.finish_session(db, user_id=cu.user_id, session_id=session_id)
    return FinishedSessionOut.from_finished(finished)


@router.post("/{session_id}/sets/bulk", response_model=LoggedSetsOut, status_code=201)
async def log_sets(
    session_id: uuid.UUID,
    payload: SetBulkCreate,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> LoggedSetsOut:
    """Log many sets into one session transactionally, with a PR verdict for each."""
    logged = await sets.log_sets(
        db,
        user_id=cu.user_id,
        session_id=session_id,
        drafts=[sets.SetDraft(**draft.model_dump()) for draft in payload.sets],
    )
    return LoggedSetsOut(items=[LoggedSetOut.from_logged(row) for row in logged])


@router.post("/{session_id}/sets", response_model=LoggedSetOut, status_code=201)
async def log_set(
    session_id: uuid.UUID,
    payload: SetCreate,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> LoggedSetOut:
    logged = await sets.log_set(
        db,
        user_id=cu.user_id,
        session_id=session_id,
        exercise_id=payload.exercise_id,
        set_number=payload.set_number,
        weight_kg=payload.weight_kg,
        reps=payload.reps,
        hold_seconds=payload.hold_seconds,
        rpe=payload.rpe,
        notes=payload.notes,
        is_backfill=payload.is_backfill,
        client_key=payload.client_key,
    )
    return LoggedSetOut.from_logged(logged)
