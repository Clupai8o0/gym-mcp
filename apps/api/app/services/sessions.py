"""Workout-session service: create, list (filtered), detail-with-sets, update, delete.

Every read/write is scoped to ``user_id``; a session that isn't the user's reads as
``not_found`` (we don't distinguish missing from forbidden for other users' rows).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.models import Exercise, ExerciseSet, WorkoutSession

# Fields a PATCH may change (values are already Pydantic-validated by the router).
_UPDATABLE = frozenset({"title", "type", "notes", "duration_minutes", "performed_at"})


@dataclass(frozen=True)
class SessionDetail:
    """A session plus its sets and the referenced exercises (keyed by id)."""

    session: WorkoutSession
    sets: Sequence[ExerciseSet]
    exercises: dict[uuid.UUID, Exercise]


async def _owned(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> WorkoutSession:
    session = (
        await db.execute(
            select(WorkoutSession).where(
                WorkoutSession.id == session_id, WorkoutSession.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if session is None:
        raise errors.not_found("Session not found")
    return session


async def create(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    performed_at: datetime,
    title: str | None = None,
    type: str | None = None,
    notes: str | None = None,
    duration_minutes: int | None = None,
) -> WorkoutSession:
    session = WorkoutSession(
        user_id=user_id,
        performed_at=performed_at,
        title=title,
        type=type,
        notes=notes,
        duration_minutes=duration_minutes,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


async def list_sessions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[WorkoutSession], int]:
    base = select(WorkoutSession).where(WorkoutSession.user_id == user_id)
    if type:
        base = base.where(WorkoutSession.type == type)
    if date_from:
        base = base.where(WorkoutSession.performed_at >= date_from)
    if date_to:
        base = base.where(WorkoutSession.performed_at <= date_to)

    total = (
        await db.execute(select(func.count()).select_from(base.order_by(None).subquery()))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                base.order_by(WorkoutSession.performed_at.desc()).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return rows, total


async def get(db: AsyncSession, *, user_id: uuid.UUID, session_id: uuid.UUID) -> SessionDetail:
    """Return the session with its sets (ordered) and the exercises they reference."""
    session = await _owned(db, user_id, session_id)

    sets = (
        (
            await db.execute(
                select(ExerciseSet)
                .where(ExerciseSet.session_id == session_id)
                .order_by(ExerciseSet.exercise_id, ExerciseSet.set_number)
            )
        )
        .scalars()
        .all()
    )

    exercises: dict[uuid.UUID, Exercise] = {}
    exercise_ids = {s.exercise_id for s in sets}
    if exercise_ids:
        rows = (
            (await db.execute(select(Exercise).where(Exercise.id.in_(exercise_ids))))
            .scalars()
            .all()
        )
        exercises = {ex.id: ex for ex in rows}

    return SessionDetail(session=session, sets=sets, exercises=exercises)


async def update(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    changes: Mapping[str, Any],
) -> WorkoutSession:
    session = await _owned(db, user_id, session_id)
    for key, value in changes.items():
        if key not in _UPDATABLE:
            raise errors.validation(f"Field '{key}' is not updatable")
        setattr(session, key, value)
    await db.flush()
    await db.refresh(session)
    return session


async def delete(db: AsyncSession, *, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
    """Delete a session (its sets cascade via the FK). Idempotent per ownership check."""
    await _owned(db, user_id, session_id)
    await db.execute(sa_delete(WorkoutSession).where(WorkoutSession.id == session_id))
    await db.flush()
