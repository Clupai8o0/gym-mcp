"""Set logging + PR detection — the domain heart of the app (docs/03).

PR detection is implemented as a **chronological recompute** over all of a user's sets
for one exercise. ``log_set``, ``update_set`` and ``delete_set`` mutate the set rows then
call :func:`_recompute`, which re-derives each set's ``is_pr``/``pr_type`` flags and the
canonical ``personal_records`` bests. One code path means log/edit/delete can never drift.

Detection priority for each set (ported from the legacy app, now keyed on ``exercise_id``):

1. **hold_time** — a longer ``hold_seconds`` than any prior hold.
2. **weight** then **reps** — only when the set has *both* weight and reps; a heavier
   weight wins, otherwise more reps than any prior best.
3. **first_log** — the very first recorded set for the exercise (no records yet),
   collapsed to a concrete metric (weight → reps → hold) for the stored record.

A metric only counts once it has appeared: logging a heavier weight-only set never
registers a weight PR (weight PRs require reps), matching the legacy contract.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.models import Exercise, ExerciseSet, PersonalRecord, WorkoutSession

# Concrete record metrics and their stored units.
_UNIT_BY_METRIC = {"weight": "kg", "reps": "reps", "hold_time": "s"}
_METRICS = ("weight", "reps", "hold_time")

# Set fields a PATCH may change (already Pydantic-validated by the router).
_UPDATABLE = frozenset({"set_number", "weight_kg", "reps", "hold_seconds", "rpe", "notes"})


@dataclass(frozen=True)
class PrOutcome:
    """The PR verdict for a single set."""

    is_pr: bool
    pr_type: str | None  # 'weight' | 'reps' | 'hold_time' | 'first_log' | None
    previous_best: Decimal | None
    new_value: Decimal | None


@dataclass(frozen=True)
class LoggedSet:
    """A set plus its PR verdict — the return of log/update."""

    set: ExerciseSet
    pr: PrOutcome


def _to_decimal(value: float | int | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


async def _assert_session_owned(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
) -> None:
    owned = (
        await db.execute(
            select(WorkoutSession.id).where(
                WorkoutSession.id == session_id, WorkoutSession.user_id == user_id
            )
        )
    ).first()
    if owned is None:
        raise errors.not_found("Session not found")


async def _assert_exercise_visible(
    db: AsyncSession, user_id: uuid.UUID, exercise_id: uuid.UUID
) -> None:
    visible = (
        await db.execute(
            select(Exercise.id).where(
                Exercise.id == exercise_id,
                or_(
                    Exercise.created_by_user_id.is_(None),
                    Exercise.created_by_user_id == user_id,
                ),
            )
        )
    ).first()
    if visible is None:
        raise errors.not_found("Exercise not found")


def _require_measurement(
    weight_kg: Decimal | None, reps: int | None, hold_seconds: int | None
) -> None:
    if weight_kg is None and reps is None and hold_seconds is None:
        raise errors.validation("A set needs at least one of weight_kg, reps, or hold_seconds")
    if weight_kg is not None and weight_kg < 0:
        raise errors.validation("weight_kg cannot be negative")
    if reps is not None and reps < 0:
        raise errors.validation("reps cannot be negative")
    if hold_seconds is not None and hold_seconds < 0:
        raise errors.validation("hold_seconds cannot be negative")


@dataclass
class _RecordState:
    value: Decimal
    achieved_at: Any
    session_id: uuid.UUID


def _evaluate(
    weight: Decimal | None,
    reps: int | None,
    hold: int | None,
    *,
    best_weight: Decimal | None,
    best_reps: Decimal | None,
    best_hold: Decimal | None,
    any_record_yet: bool,
) -> tuple[str, Decimal] | None:
    """Return ``(pr_type, new_value)`` for one set given the running bests, or ``None``.

    ``pr_type`` is the value stored on the set ('first_log' included); the caller maps it
    to a concrete metric for ``personal_records``.
    """
    if hold is not None:
        hold_d = Decimal(hold)
        if best_hold is None or hold_d > best_hold:
            return "hold_time", hold_d

    if weight is not None and reps is not None:
        if best_weight is None or weight > best_weight:
            return "weight", weight
        reps_d = Decimal(reps)
        if best_reps is None or reps_d > best_reps:
            return "reps", reps_d

    if not any_record_yet:
        first = weight if weight is not None else _first_int(reps, hold)
        if first is not None:
            return "first_log", first

    return None


def _first_int(reps: int | None, hold: int | None) -> Decimal | None:
    if reps is not None:
        return Decimal(reps)
    if hold is not None:
        return Decimal(hold)
    return None


def _concrete_metric(
    pr_type: str, weight: Decimal | None, reps: int | None, hold: int | None
) -> str:
    if pr_type != "first_log":
        return pr_type
    if weight is not None:
        return "weight"
    if reps is not None:
        return "reps"
    return "hold_time"


async def _recompute(
    db: AsyncSession, user_id: uuid.UUID, exercise_id: uuid.UUID
) -> dict[uuid.UUID, PrOutcome]:
    """Re-derive set PR flags + ``personal_records`` bests for one (user, exercise).

    Returns each set's :class:`PrOutcome` keyed by set id so callers can report the
    verdict for the set they just touched.
    """
    rows = (
        await db.execute(
            select(ExerciseSet, WorkoutSession.performed_at)
            .join(WorkoutSession, ExerciseSet.session_id == WorkoutSession.id)
            .where(ExerciseSet.user_id == user_id, ExerciseSet.exercise_id == exercise_id)
            .order_by(
                WorkoutSession.performed_at,
                ExerciseSet.created_at,
                ExerciseSet.set_number,
                ExerciseSet.id,
            )
        )
    ).all()

    best: dict[str, Decimal | None] = {"weight": None, "reps": None, "hold_time": None}
    records: dict[str, _RecordState] = {}
    any_record_yet = False
    outcomes: dict[uuid.UUID, PrOutcome] = {}

    for exercise_set, performed_at in rows:
        weight = exercise_set.weight_kg
        reps = exercise_set.reps
        hold = exercise_set.hold_seconds

        verdict = _evaluate(
            weight,
            reps,
            hold,
            best_weight=best["weight"],
            best_reps=best["reps"],
            best_hold=best["hold_time"],
            any_record_yet=any_record_yet,
        )

        if verdict is None:
            exercise_set.is_pr = False
            exercise_set.pr_type = None
            outcomes[exercise_set.id] = PrOutcome(False, None, None, None)
            continue

        pr_type, new_value = verdict
        metric = _concrete_metric(pr_type, weight, reps, hold)
        previous_best = best[metric]

        best[metric] = new_value
        records[metric] = _RecordState(
            value=new_value, achieved_at=performed_at, session_id=exercise_set.session_id
        )
        any_record_yet = True

        exercise_set.is_pr = True
        exercise_set.pr_type = pr_type
        outcomes[exercise_set.id] = PrOutcome(True, pr_type, previous_best, new_value)

    await _sync_records(db, user_id, exercise_id, records)
    await db.flush()
    return outcomes


async def _sync_records(
    db: AsyncSession,
    user_id: uuid.UUID,
    exercise_id: uuid.UUID,
    records: Mapping[str, _RecordState],
) -> None:
    existing = {
        pr.pr_type: pr
        for pr in (
            await db.execute(
                select(PersonalRecord).where(
                    PersonalRecord.user_id == user_id, PersonalRecord.exercise_id == exercise_id
                )
            )
        )
        .scalars()
        .all()
    }
    for metric in _METRICS:
        state = records.get(metric)
        current = existing.get(metric)
        if state is None:
            if current is not None:
                await db.delete(current)
            continue
        if current is None:
            db.add(
                PersonalRecord(
                    user_id=user_id,
                    exercise_id=exercise_id,
                    pr_type=metric,
                    value=state.value,
                    unit=_UNIT_BY_METRIC[metric],
                    achieved_at=state.achieved_at,
                    session_id=state.session_id,
                )
            )
        else:
            current.value = state.value
            current.unit = _UNIT_BY_METRIC[metric]
            current.achieved_at = state.achieved_at
            current.session_id = state.session_id


async def log_set(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    exercise_id: uuid.UUID,
    set_number: int,
    weight_kg: float | None = None,
    reps: int | None = None,
    hold_seconds: int | None = None,
    rpe: float | None = None,
    notes: str | None = None,
) -> LoggedSet:
    """Insert a set, auto-detect + upsert PRs, and return the set with its PR verdict."""
    await _assert_session_owned(db, user_id, session_id)
    await _assert_exercise_visible(db, user_id, exercise_id)

    weight_d = _to_decimal(weight_kg)
    _require_measurement(weight_d, reps, hold_seconds)

    exercise_set = ExerciseSet(
        user_id=user_id,
        session_id=session_id,
        exercise_id=exercise_id,
        set_number=set_number,
        weight_kg=weight_d,
        reps=reps,
        hold_seconds=hold_seconds,
        rpe=_to_decimal(rpe),
        notes=notes,
    )
    db.add(exercise_set)
    await db.flush()

    outcomes = await _recompute(db, user_id, exercise_id)
    await db.refresh(exercise_set)
    return LoggedSet(set=exercise_set, pr=outcomes[exercise_set.id])


async def update_set(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    set_id: uuid.UUID,
    changes: Mapping[str, Any],
) -> LoggedSet:
    """Edit a set's metrics and recompute PRs for its exercise."""
    exercise_set = (
        await db.execute(
            select(ExerciseSet).where(ExerciseSet.id == set_id, ExerciseSet.user_id == user_id)
        )
    ).scalar_one_or_none()
    if exercise_set is None:
        raise errors.not_found("Set not found")

    for key, value in changes.items():
        if key not in _UPDATABLE:
            raise errors.validation(f"Field '{key}' is not updatable")
        if key in ("weight_kg", "rpe"):
            value = _to_decimal(value)
        setattr(exercise_set, key, value)

    _require_measurement(exercise_set.weight_kg, exercise_set.reps, exercise_set.hold_seconds)
    await db.flush()

    outcomes = await _recompute(db, user_id, exercise_set.exercise_id)
    await db.refresh(exercise_set)
    return LoggedSet(set=exercise_set, pr=outcomes[exercise_set.id])


async def delete_set(db: AsyncSession, *, user_id: uuid.UUID, set_id: uuid.UUID) -> None:
    """Delete a set and recompute PRs for its exercise."""
    exercise_set = (
        await db.execute(
            select(ExerciseSet).where(ExerciseSet.id == set_id, ExerciseSet.user_id == user_id)
        )
    ).scalar_one_or_none()
    if exercise_set is None:
        raise errors.not_found("Set not found")

    exercise_id = exercise_set.exercise_id
    await db.execute(sa_delete(ExerciseSet).where(ExerciseSet.id == set_id))
    await db.flush()
    await _recompute(db, user_id, exercise_id)


async def list_session_sets(
    db: AsyncSession, *, user_id: uuid.UUID, session_id: uuid.UUID
) -> Sequence[ExerciseSet]:
    """All sets for a session, ordered by exercise then set number (ownership-checked)."""
    await _assert_session_owned(db, user_id, session_id)
    return (
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
