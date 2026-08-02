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

from sqlalchemy import func, select
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


async def volume(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    date_from: datetime,
    date_to: datetime,
    exercise_id: uuid.UUID | None = None,
) -> Sequence[VolumeBucket]:
    """Total sets, reps, and tonnage per exercise between two instants (inclusive).

    Aggregated in SQL. It used to select one row per *set* and fold them in Python, so a year's
    range shipped thousands of rows across the wire to produce a few dozen — and the cost grew
    with training history rather than with the answer. Now Postgres returns one row per exercise.

    Two details in the SQL carry the original semantics exactly:

    * ``coalesce`` around each ``sum`` — an empty group would otherwise be ``NULL``, and ``None``
      already means something specific in this API (see below).
    * ``bool_or(weight_kg IS NULL)`` — tonnage is reported as ``None``, not a smaller number, when
      *any* set in the group was bodyweight. A partial tonnage looks like a real total and would
      quietly understate the work done.
    """
    if date_from > date_to:
        raise errors.validation("date_from must be on or before date_to")

    stmt = (
        select(
            ExerciseSet.exercise_id,
            Exercise.name,
            func.count().label("total_sets"),
            func.coalesce(func.sum(func.coalesce(ExerciseSet.reps, 0)), 0).label("total_reps"),
            # NULL × anything is NULL, so a bodyweight set or one with no reps contributes 0 —
            # the same two guards the Python version spelled out as branches.
            func.coalesce(
                func.sum(func.coalesce(ExerciseSet.weight_kg * ExerciseSet.reps, 0)), 0
            ).label("tonnage"),
            func.bool_or(ExerciseSet.weight_kg.is_(None)).label("has_bodyweight"),
        )
        .join(WorkoutSession, ExerciseSet.session_id == WorkoutSession.id)
        .join(Exercise, ExerciseSet.exercise_id == Exercise.id)
        .where(
            ExerciseSet.user_id == user_id,
            WorkoutSession.performed_at >= date_from,
            WorkoutSession.performed_at <= date_to,
        )
        .group_by(ExerciseSet.exercise_id, Exercise.name)
    )
    if exercise_id is not None:
        stmt = stmt.where(ExerciseSet.exercise_id == exercise_id)

    result = [
        VolumeBucket(
            exercise_id=ex_id,
            exercise_name=name,
            total_sets=total_sets,
            total_reps=total_reps,
            total_tonnage_kg=None if has_bodyweight else round(float(tonnage), 3),
        )
        for ex_id, name, total_sets, total_reps, tonnage, has_bodyweight in (
            await db.execute(stmt)
        ).all()
    ]
    # Sorted in Python, deliberately: the database orders by its collation, which disagrees with
    # Python's codepoint order on case and punctuation. Letting it sort would silently change the
    # sequence MCP clients already see.
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
