"""Workout-session service: create, list (filtered), detail-with-sets, update, delete,
plus the **session lifecycle** (finish / resolve-the-active-one).

Every read/write is scoped to ``user_id``; a session that isn't the user's reads as
``not_found`` (we don't distinguish missing from forbidden for other users' rows).

**Lifecycle (Phase 11A).** ``ended_at IS NULL`` — nothing else — means "in progress".
There is deliberately **no date arithmetic** here: the old "is ``performed_at`` today?"
heuristic ran in the server's timezone (UTC in production), so a 5 pm session in UTC−8
was already "tomorrow" and a finished morning workout still read "in progress" at 11 pm.
Dangling sessions are retired lazily on read — see :func:`get_active_session`.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.models import Exercise, ExerciseSet, WorkoutSession

# Fields a PATCH may change (values are already Pydantic-validated by the router).
_UPDATABLE = frozenset({"title", "type", "notes", "duration_minutes", "performed_at"})

# How long a session may sit untouched before a read considers it abandoned (D31). Chosen so
# it can never fire mid-workout (no session runs 12 h) but a forgotten one can't survive a
# night's sleep and swallow tomorrow's training.
STALE_AFTER = timedelta(hours=12)


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


# ── Lifecycle ────────────────────────────────────────────────────────────────────────
def _duration_minutes(performed_at: datetime, ended_at: datetime) -> int:
    """Whole minutes between start and end, never negative (a clock skew must not go < 0)."""
    return max(0, round((ended_at - performed_at).total_seconds() / 60))


async def _last_activity(db: AsyncSession, session: WorkoutSession) -> datetime:
    """When the session was last touched: its newest set, or its start if it has none."""
    newest = (
        await db.execute(
            select(func.max(ExerciseSet.created_at)).where(ExerciseSet.session_id == session.id)
        )
    ).scalar_one_or_none()
    if newest is None:
        return session.performed_at
    return max(newest, session.performed_at)


async def _stamp_finished(
    db: AsyncSession, session: WorkoutSession, ended_at: datetime
) -> WorkoutSession:
    session.ended_at = ended_at
    session.duration_minutes = _duration_minutes(session.performed_at, ended_at)
    await db.flush()
    await db.refresh(session)
    return session


async def finish_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    ended_at: datetime | None = None,
) -> WorkoutSession:
    """Close a session: stamp ``ended_at`` and store the derived ``duration_minutes``.

    **Idempotent** — finishing an already-finished session returns it untouched rather than
    raising, so a double-tap (or a retried offline write) is harmless. Cross-user scoping is
    the same as everywhere else: someone else's session is ``not_found``.
    """
    session = await _owned(db, user_id, session_id)
    if session.ended_at is not None:
        return session
    return await _stamp_finished(db, session, ended_at or datetime.now(tz=UTC))


async def get_active_session(
    db: AsyncSession, *, user_id: uuid.UUID, now: datetime | None = None
) -> WorkoutSession | None:
    """The user's in-progress session, or ``None``.

    "In progress" is ``ended_at IS NULL`` — no timezone, no date comparison. Sessions left
    open are retired here rather than by a background job (there is none on Fluid Compute):
    any open session untouched for :data:`STALE_AFTER` is finished as of its **last
    activity** (newest set, else its start), so the duration reflects the training that
    happened and not the hours it sat forgotten. The newest still-live session is returned
    (D31).
    """
    at = now or datetime.now(tz=UTC)
    open_sessions = (
        (
            await db.execute(
                select(WorkoutSession)
                .where(WorkoutSession.user_id == user_id, WorkoutSession.ended_at.is_(None))
                .order_by(WorkoutSession.performed_at.desc())
            )
        )
        .scalars()
        .all()
    )

    active: WorkoutSession | None = None
    for session in open_sessions:
        touched = await _last_activity(db, session)
        if at - touched > STALE_AFTER:
            await _stamp_finished(db, session, touched)
        elif active is None:
            active = session
    return active
