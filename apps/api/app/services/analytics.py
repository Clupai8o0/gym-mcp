"""Analytics: training volume by exercise and session frequency by ISO week.

Volume tonnage sums ``weight_kg × reps`` per exercise, but is reported as ``None`` when
any set in the range was bodyweight (null weight) — a partial tonnage would mislead.
Frequency counts sessions into Monday-anchored weekly buckets for the last N weeks.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.models import Exercise, ExerciseSet, WorkoutSession


@dataclass(frozen=True)
class VolumeBucket:
    exercise_id: uuid.UUID
    exercise_name: str
    total_sets: int
    total_reps: int
    total_tonnage_kg: float | None


@dataclass(frozen=True)
class WeekCount:
    week_start: date
    count: int


class _Accum:
    __slots__ = ("exercise_name", "total_sets", "total_reps", "tonnage", "has_bodyweight")

    def __init__(self, exercise_name: str) -> None:
        self.exercise_name = exercise_name
        self.total_sets = 0
        self.total_reps = 0
        self.tonnage = 0.0
        self.has_bodyweight = False


async def volume(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    date_from: datetime,
    date_to: datetime,
    exercise_id: uuid.UUID | None = None,
) -> Sequence[VolumeBucket]:
    """Total sets, reps, and tonnage per exercise between two instants (inclusive)."""
    if date_from > date_to:
        raise errors.validation("date_from must be on or before date_to")

    stmt = (
        select(
            ExerciseSet.exercise_id,
            Exercise.name,
            ExerciseSet.weight_kg,
            ExerciseSet.reps,
        )
        .join(WorkoutSession, ExerciseSet.session_id == WorkoutSession.id)
        .join(Exercise, ExerciseSet.exercise_id == Exercise.id)
        .where(
            ExerciseSet.user_id == user_id,
            WorkoutSession.performed_at >= date_from,
            WorkoutSession.performed_at <= date_to,
        )
    )
    if exercise_id is not None:
        stmt = stmt.where(ExerciseSet.exercise_id == exercise_id)

    buckets: dict[uuid.UUID, _Accum] = {}
    for ex_id, name, weight_kg, reps in (await db.execute(stmt)).all():
        acc = buckets.get(ex_id)
        if acc is None:
            acc = _Accum(name)
            buckets[ex_id] = acc
        acc.total_sets += 1
        acc.total_reps += reps or 0
        if weight_kg is None:
            acc.has_bodyweight = True
        elif reps is not None:
            acc.tonnage += float(weight_kg) * reps

    result = [
        VolumeBucket(
            exercise_id=ex_id,
            exercise_name=acc.exercise_name,
            total_sets=acc.total_sets,
            total_reps=acc.total_reps,
            total_tonnage_kg=None if acc.has_bodyweight else round(acc.tonnage, 3),
        )
        for ex_id, acc in buckets.items()
    ]
    result.sort(key=lambda b: b.exercise_name)
    return result


def _monday_of(moment: datetime) -> date:
    """The Monday (UTC date) of the week containing ``moment``."""
    day = moment.astimezone(UTC).date()
    return day - timedelta(days=day.weekday())


async def frequency(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    weeks: int = 8,
    now: datetime | None = None,
) -> Sequence[WeekCount]:
    """Sessions per ISO week for the last ``weeks`` weeks (Monday-anchored, zero-filled)."""
    if not 1 <= weeks <= 52:
        raise errors.validation("weeks must be between 1 and 52")

    current = now or datetime.now(tz=UTC)
    start_monday = _monday_of(current) - timedelta(weeks=weeks - 1)

    counts: dict[date, int] = {start_monday + timedelta(weeks=i): 0 for i in range(weeks)}

    performed_ats = (
        (
            await db.execute(
                select(WorkoutSession.performed_at).where(
                    WorkoutSession.user_id == user_id,
                    WorkoutSession.performed_at
                    >= datetime.combine(start_monday, datetime.min.time(), tzinfo=UTC),
                )
            )
        )
        .scalars()
        .all()
    )
    for performed_at in performed_ats:
        bucket = _monday_of(performed_at)
        if bucket in counts:
            counts[bucket] += 1

    return [WeekCount(week_start=week, count=counts[week]) for week in sorted(counts)]
