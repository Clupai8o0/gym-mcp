"""Personal-record response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.schemas.sets import SetOut

if TYPE_CHECKING:
    from app.services.prs import PrWithExercise


class PrOut(BaseModel):
    id: uuid.UUID
    exercise_id: uuid.UUID
    exercise_name: str
    exercise_slug: str
    pr_type: str
    value: float
    unit: str
    achieved_at: datetime
    session_id: uuid.UUID | None
    notes: str | None

    @classmethod
    def from_pair(cls, row: PrWithExercise) -> PrOut:
        return cls(
            id=row.pr.id,
            exercise_id=row.pr.exercise_id,
            exercise_name=row.exercise.name,
            exercise_slug=row.exercise.slug,
            pr_type=row.pr.pr_type,
            value=float(row.pr.value),
            unit=row.pr.unit,
            achieved_at=row.pr.achieved_at,
            session_id=row.pr.session_id,
            notes=row.pr.notes,
        )


class PrListOut(BaseModel):
    items: list[PrOut]


class PrHistoryOut(BaseModel):
    exercise_id: uuid.UUID
    pr_type: str
    items: list[SetOut]
