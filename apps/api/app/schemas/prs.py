"""Personal-record request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.models import PersonalRecordHistory
    from app.services.prs import PrWithExercise


class PrCreate(BaseModel):
    """A hand-entered record. ``unit`` is not a field — it follows from ``pr_type``."""

    exercise_id: uuid.UUID
    pr_type: str
    value: float
    achieved_at: datetime
    session_id: uuid.UUID | None = None
    notes: str | None = None


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
    #: ``auto`` (derived from a logged set) or ``manual`` (entered by hand). Clients that show a
    #: record should say which — an estimated 1RM is not the same claim as a set you performed.
    source: str
    # Exercise art, so the Dashboard can show each record with its illustration (docs/07 §Dashboard)
    # without an N+1 fetch. Additive; both REST and the MCP ``get_prs`` tool serialize this schema.
    illustration_url: str | None
    illustration_status: str
    is_custom: bool

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
            source=row.pr.source,
            illustration_url=row.exercise.illustration_url,
            illustration_status=row.exercise.illustration_status,
            is_custom=row.exercise.created_by_user_id is not None,
        )


class PrListOut(BaseModel):
    items: list[PrOut]


class PrHistoryItem(BaseModel):
    """One entry in a record's chronology, auto or manual.

    This replaces the ``SetOut`` this endpoint used to return. A manual record has no set behind
    it, so a set-shaped payload could not represent one — which is precisely why manual entries
    were missing from PR history before.
    """

    id: uuid.UUID
    pr_type: str
    value: float
    unit: str
    achieved_at: datetime
    source: str
    #: The set that earned an ``auto`` entry; ``null`` for a manual one.
    set_id: uuid.UUID | None
    session_id: uuid.UUID | None
    notes: str | None

    @classmethod
    def from_row(cls, row: PersonalRecordHistory) -> PrHistoryItem:
        return cls(
            id=row.id,
            pr_type=row.pr_type,
            value=float(row.value),
            unit=row.unit,
            achieved_at=row.achieved_at,
            source=row.source,
            set_id=row.set_id,
            session_id=row.session_id,
            notes=row.notes,
        )


class PrHistoryOut(BaseModel):
    exercise_id: uuid.UUID
    pr_type: str
    items: list[PrHistoryItem] = Field(
        description="Oldest first; manual and auto entries interleaved chronologically."
    )
