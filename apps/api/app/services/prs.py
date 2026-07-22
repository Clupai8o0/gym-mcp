"""Personal-record reads. Writes happen only via PR detection in ``services/sets``."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Exercise, ExerciseSet, PersonalRecord


@dataclass(frozen=True)
class PrWithExercise:
    """A personal record paired with the exercise it belongs to (for display)."""

    pr: PersonalRecord
    exercise: Exercise


async def list_prs(
    db: AsyncSession, *, user_id: uuid.UUID, exercise_id: uuid.UUID | None = None
) -> Sequence[PrWithExercise]:
    """All of a user's PRs (optionally one exercise), ordered by exercise name then type."""
    stmt = (
        select(PersonalRecord, Exercise)
        .join(Exercise, PersonalRecord.exercise_id == Exercise.id)
        .where(PersonalRecord.user_id == user_id)
        .order_by(Exercise.name, PersonalRecord.pr_type)
    )
    if exercise_id is not None:
        stmt = stmt.where(PersonalRecord.exercise_id == exercise_id)
    rows = (await db.execute(stmt)).all()
    return [PrWithExercise(pr=pr, exercise=ex) for pr, ex in rows]


async def history(
    db: AsyncSession, *, user_id: uuid.UUID, exercise_id: uuid.UUID, pr_type: str
) -> Sequence[ExerciseSet]:
    """Chronological list of the PR-setting sets for one exercise + pr_type."""
    return (
        (
            await db.execute(
                select(ExerciseSet)
                .where(
                    ExerciseSet.user_id == user_id,
                    ExerciseSet.exercise_id == exercise_id,
                    ExerciseSet.is_pr.is_(True),
                    ExerciseSet.pr_type == pr_type,
                )
                .order_by(ExerciseSet.created_at)
            )
        )
        .scalars()
        .all()
    )
