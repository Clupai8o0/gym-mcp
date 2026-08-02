"""Workout-session service: create, list (filtered), detail-with-sets, update, delete,
plus the **session lifecycle** (finish / resolve-the-active-one).

Every read/write is scoped to ``user_id``; a session that isn't the user's reads as
``not_found`` (we don't distinguish missing from forbidden for other users' rows).

**Lifecycle (Phase 11A).** ``ended_at IS NULL`` — nothing else — means "in progress".
Dangling sessions are retired lazily on read — see :func:`get_active_session`.

**Backdated sessions are born finished.** ``log_session`` used to leave ``ended_at`` null
whatever it was handed, so recording last Tuesday's workout made it "in progress" and the
session bar offered to resume a workout from three months ago. :func:`create` now closes a
session at creation when it plainly is not a live one.

The test for "plainly not live" is a **rolling window**, never "is ``performed_at`` today?".
That calendar question is precisely the bug Phase 11A removed: it ran in the server's timezone
(UTC in production), so a 5 pm session in UTC−8 was already "tomorrow" and a finished morning
workout still read "in progress" at 11 pm. A window measured in hours means the same thing in
every timezone, needs nothing from the client, and answers the question actually being asked —
*could this still be happening?* — rather than *what day is it where the server is?*
:data:`STALE_AFTER` is that window, reused so a session can never be created open and then be
considered abandoned by the very next read.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock, errors
from app.models import Exercise, ExerciseSet, WorkoutSession

# Fields a PATCH may change (values are already Pydantic-validated by the router).
_UPDATABLE = frozenset({"title", "type", "notes", "duration_minutes", "performed_at", "ended_at"})

# How long a session may sit untouched before a read considers it abandoned (D31). Chosen so
# it can never fire mid-workout (no session runs 12 h) but a forgotten one can't survive a
# night's sleep and swallow tomorrow's training. Doubles as the window inside which a session
# being created is still plausibly live (see the module docstring).
STALE_AFTER = timedelta(hours=12)

# The ceiling on a duration the app *derives* rather than one the caller stated. A session left
# open for a week and then finished would otherwise record 136,070 minutes of training and skew
# every average built on it. An explicitly supplied `duration_minutes` is never clamped — that is
# the caller's own claim about their workout.
MAX_DERIVED_DURATION = timedelta(hours=8)


@dataclass(frozen=True)
class SessionDetail:
    """A session plus its sets and the referenced exercises (keyed by id)."""

    session: WorkoutSession
    sets: Sequence[ExerciseSet]
    exercises: dict[uuid.UUID, Exercise]


@dataclass(frozen=True)
class ActiveSession:
    """The in-progress session and how many sets are in it so far.

    The count travels with the session because every caller that asks "am I training?" also
    wants to say *how far in* — the docked session bar and the home workout card both do. It
    is free here: :func:`_activity` already scans this session's sets to decide whether the
    session is stale, so it counts them in the same statement.
    """

    session: WorkoutSession
    set_count: int


async def _owned(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    *,
    include_deleted: bool = False,
) -> WorkoutSession:
    stmt = select(WorkoutSession).where(
        WorkoutSession.id == session_id, WorkoutSession.user_id == user_id
    )
    if not include_deleted:
        stmt = stmt.where(WorkoutSession.deleted_at.is_(None))
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session is None:
        raise errors.not_found("Session not found")
    return session


def _closes_immediately(
    performed_at: datetime, duration_minutes: int | None, *, at: datetime
) -> datetime | None:
    """The ``ended_at`` a session should be born with, or ``None`` to leave it in progress.

    Two ways a session is finished the moment it is recorded:

    * a **duration was stated** — the caller is describing a workout that already happened, and
      its end follows arithmetically;
    * it **started too long ago to still be running** — recording last Tuesday's session is
      bookkeeping, not the start of a workout, so it ends where it started.

    Anything inside the window with no duration is a genuine "I am training now", and stays open
    until ``finish_session`` or the stale sweep closes it.
    """
    if duration_minutes is not None:
        return performed_at + timedelta(minutes=duration_minutes)
    if at - performed_at > STALE_AFTER:
        return performed_at
    return None


async def create(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    performed_at: datetime,
    title: str | None = None,
    type: str | None = None,
    notes: str | None = None,
    duration_minutes: int | None = None,
    client_key: str | None = None,
    now: datetime | None = None,
) -> WorkoutSession:
    """Record a session. ``client_key`` makes a retry return the original instead of a duplicate.

    Which is not hypothetical: a retried call that never saw its response left two identical
    `upper_hypertrophy` sessions dated 1 May, and nothing could tell them apart afterwards.
    """
    if client_key is not None:
        replay = (
            await db.execute(
                select(WorkoutSession).where(
                    WorkoutSession.user_id == user_id, WorkoutSession.client_key == client_key
                )
            )
        ).scalar_one_or_none()
        if replay is not None:
            return replay

    started = clock.as_utc(performed_at)
    session = WorkoutSession(
        user_id=user_id,
        performed_at=started,
        title=title,
        type=type,
        notes=notes,
        duration_minutes=duration_minutes,
        ended_at=_closes_immediately(started, duration_minutes, at=now or clock.now()),
        client_key=client_key,
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
    include_deleted: bool = False,
) -> tuple[Sequence[WorkoutSession], int]:
    base = select(WorkoutSession).where(WorkoutSession.user_id == user_id)
    if not include_deleted:
        base = base.where(WorkoutSession.deleted_at.is_(None))
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
                .where(
                    ExerciseSet.session_id == session_id,
                    ExerciseSet.deleted_at.is_(None),
                )
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
    clear_notes: bool = False,
) -> WorkoutSession:
    """Patch session metadata. Only the supplied keys change.

    ``clear_notes`` exists because ``None`` already means "leave alone" in a partial update, and
    overloading it would make "remove the note" unsayable. Same reasoning would apply to any other
    nullable field that grows a need to be emptied.

    Correcting ``performed_at`` or ``duration_minutes`` on a **finished** session also moves its
    ``ended_at``, so the row stays internally consistent — fixing a mistyped duration should not
    leave an end time that contradicts it. Passing ``ended_at`` explicitly wins over that
    derivation: the caller is stating the end, not asking for one. A session still in progress
    keeps its null ``ended_at``: it ends when it ends.

    Moving ``performed_at`` also moves any hand-entered record pinned to this session, and
    recomputes the records for every exercise it touched — a session's date is *when its sets
    happened*, so changing it reorders the chronology those records are derived from.
    """
    session = await _owned(db, user_id, session_id)
    for key, value in changes.items():
        if key not in _UPDATABLE:
            raise errors.validation(f"Field '{key}' is not updatable")
        if key in ("performed_at", "ended_at") and value is not None:
            value = clock.as_utc(value)
        setattr(session, key, value)
    if clear_notes:
        session.notes = None

    stated_end = changes.get("ended_at") is not None
    if (
        not stated_end
        and session.ended_at is not None
        and {"performed_at", "duration_minutes"} & set(changes)
    ):
        session.ended_at = (
            session.performed_at + timedelta(minutes=session.duration_minutes)
            if session.duration_minutes is not None
            else max(session.ended_at, session.performed_at)
        )

    await db.flush()

    if "performed_at" in changes:
        # Imported here rather than at module scope: `integrity` imports `sets`, which is a
        # sibling service, and a top-level import would make sessions↔sets↔integrity circular.
        from app.services import integrity

        await integrity.cascade_achieved_at(db, user_id=user_id, session_id=session_id)
        for exercise_id in await integrity.exercises_touched_by_session(
            db, user_id=user_id, session_id=session_id
        ):
            await _recompute_exercise(db, user_id, exercise_id)

    await db.refresh(session)
    return session


async def _recompute_exercise(db: AsyncSession, user_id: uuid.UUID, exercise_id: uuid.UUID) -> None:
    from app.services import sets as sets_service

    await sets_service.recompute(db, user_id=user_id, exercise_id=exercise_id)


@dataclass(frozen=True)
class SessionDeletion:
    """What a delete did (or, under ``dry_run``, would do)."""

    session: WorkoutSession
    set_count: int
    exercises_recalculated: int
    dry_run: bool


async def delete(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    cascade: bool = True,
    dry_run: bool = False,
    at: datetime | None = None,
) -> SessionDeletion:
    """Soft-delete a session and, with ``cascade``, its sets — then recalculate every PR affected.

    Refusing without ``cascade`` when sets exist is not pedantry: a session and its sets are one
    workout, and removing the header while leaving the rows would leave sets that still count
    toward records and volume but belong to a workout that no longer happened. The refusal says
    how many, so the caller can decide with the number in front of them.
    """
    session = await _owned(db, user_id, session_id)
    from app.services import integrity

    exercise_ids = await integrity.exercises_touched_by_session(
        db, user_id=user_id, session_id=session_id
    )
    live_sets = (
        await db.execute(
            select(func.count()).where(
                ExerciseSet.session_id == session_id, ExerciseSet.deleted_at.is_(None)
            )
        )
    ).scalar_one()

    if live_sets and not cascade:
        raise errors.validation(
            f"This session has {live_sets} set{'s' if live_sets != 1 else ''}. Pass cascade=true "
            f"to delete them with it, or delete them individually first.",
            session_id=str(session_id),
            set_count=live_sets,
        )

    if dry_run:
        return SessionDeletion(
            session=session,
            set_count=live_sets,
            exercises_recalculated=len(exercise_ids),
            dry_run=True,
        )

    stamp = at or clock.now()
    session.deleted_at = stamp
    if cascade:
        for row in (
            (
                await db.execute(
                    select(ExerciseSet).where(
                        ExerciseSet.session_id == session_id, ExerciseSet.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        ):
            row.deleted_at = stamp
    await db.flush()

    for exercise_id in exercise_ids:
        await _recompute_exercise(db, user_id, exercise_id)

    return SessionDeletion(
        session=session,
        set_count=live_sets,
        exercises_recalculated=len(exercise_ids),
        dry_run=False,
    )


# ── Lifecycle ────────────────────────────────────────────────────────────────────────
def _duration_minutes(performed_at: datetime, ended_at: datetime) -> int:
    """Whole minutes between start and end, never negative (a clock skew must not go < 0),
    and never longer than :data:`MAX_DERIVED_DURATION`.

    The ceiling is what stops a session that was left open and finished days later from
    recording 136,070 minutes. It applies only to a duration derived here; one the caller
    stated is theirs and is never touched (see :func:`_stamp_finished`).
    """
    minutes = max(0, round((ended_at - performed_at).total_seconds() / 60))
    return min(minutes, int(MAX_DERIVED_DURATION.total_seconds() // 60))


async def _activity(db: AsyncSession, session: WorkoutSession) -> tuple[datetime, int]:
    """When the session was last touched, and how many sets it holds.

    Both answers come from one aggregate over the same rows: the staleness sweep needs the
    newest ``created_at``, and every caller of :func:`get_active` needs the count, so asking
    for them separately would be two round trips for one scan.
    """
    newest, count = (
        await db.execute(
            select(func.max(ExerciseSet.created_at), func.count()).where(
                ExerciseSet.session_id == session.id, ExerciseSet.deleted_at.is_(None)
            )
        )
    ).one()
    if newest is None:
        return session.performed_at, count
    return max(newest, session.performed_at), count


async def _stamp_finished(
    db: AsyncSession, session: WorkoutSession, ended_at: datetime
) -> WorkoutSession:
    """Close a session, deriving its duration **only if the caller never stated one**.

    A ``duration_minutes`` passed to ``log_session`` is a fact the user supplied about their own
    workout. Recomputing it from wall-clock on finish threw that away and replaced it with the
    time between the start and whenever anyone happened to call ``finish_session``.
    """
    session.ended_at = ended_at
    if session.duration_minutes is None:
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
) -> ActiveSession | None:
    """The user's in-progress session **and its set count**, or ``None``.

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
                .where(
                    WorkoutSession.user_id == user_id,
                    WorkoutSession.ended_at.is_(None),
                    WorkoutSession.deleted_at.is_(None),
                )
                .order_by(WorkoutSession.performed_at.desc())
            )
        )
        .scalars()
        .all()
    )

    active: ActiveSession | None = None
    for session in open_sessions:
        touched, set_count = await _activity(db, session)
        # Two ways an open session is not the one you are training right now: nothing has
        # touched it in half a day, or it *started* longer ago than a workout can last. The
        # second covers rows created before `create` learned to close backdated sessions —
        # without it a session from three months ago stays "in progress" forever, because
        # someone adding a set to it keeps resetting the last-activity clock.
        if at - touched > STALE_AFTER or at - session.performed_at > STALE_AFTER:
            await _stamp_finished(db, session, touched)
        elif active is None:
            active = ActiveSession(session=session, set_count=set_count)
    return active
