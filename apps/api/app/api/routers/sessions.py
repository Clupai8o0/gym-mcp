"""Workout-session endpoints, including logging a set into a session."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, Pagination, current_user, get_db, pagination
from app.schemas.sessions import (
    ActiveSessionOut,
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
from app.services import sessions, sets

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
        session=SessionOut.model_validate(active.session), set_count=active.set_count
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
    )


@router.post("/{session_id}/finish", response_model=SessionOut)
async def finish_session(
    session_id: uuid.UUID,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    """Close a session and store its duration. Idempotent — finishing a finished one is a no-op."""
    session = await sessions.finish_session(db, user_id=cu.user_id, session_id=session_id)
    return SessionOut.model_validate(session)


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
