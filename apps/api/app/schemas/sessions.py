"""Workout-session request/response schemas (detail groups sets by exercise)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel, PageMeta
from app.schemas.exercises import ExerciseOut
from app.schemas.sets import SetOut

if TYPE_CHECKING:
    from app.services.sessions import SessionDetail


class SessionOut(ORMModel):
    id: uuid.UUID
    title: str | None
    type: str | None
    performed_at: datetime
    #: ``None`` while the workout is in progress; stamped by ``POST …/finish`` (Phase 11A).
    ended_at: datetime | None
    notes: str | None
    duration_minutes: int | None
    created_at: datetime


class SessionListOut(PageMeta):
    items: list[SessionOut]


class ActiveSessionOut(BaseModel):
    """The user's in-progress session, or ``null`` when they aren't training.

    Wrapped rather than returned bare so "no active session" is an ordinary 200 with a
    typed, nullable field — clients poll this on every screen and a 404 would be noise.
    """

    session: SessionOut | None


class ExerciseSetGroup(BaseModel):
    """One exercise and its sets within a session detail."""

    exercise: ExerciseOut
    sets: list[SetOut]


class SessionDetailOut(SessionOut):
    """Session plus its sets grouped by exercise (ordered by set number)."""

    exercises: list[ExerciseSetGroup]

    @classmethod
    def from_detail(cls, detail: SessionDetail) -> SessionDetailOut:
        groups: dict[uuid.UUID, list[SetOut]] = {}
        for row in detail.sets:
            groups.setdefault(row.exercise_id, []).append(SetOut.model_validate(row))

        exercises = [
            ExerciseSetGroup(
                exercise=ExerciseOut.model_validate(detail.exercises[exercise_id]),
                sets=sets,
            )
            for exercise_id, sets in groups.items()
            if exercise_id in detail.exercises
        ]
        exercises.sort(key=lambda g: g.exercise.name)

        base = SessionOut.model_validate(detail.session)
        return cls(**base.model_dump(), exercises=exercises)


class SessionCreate(BaseModel):
    performed_at: datetime
    title: str | None = Field(default=None, max_length=200)
    type: str | None = Field(default=None, max_length=50)
    notes: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0)


class SessionUpdate(BaseModel):
    """Patch session metadata; only supplied fields change."""

    performed_at: datetime | None = None
    title: str | None = Field(default=None, max_length=200)
    type: str | None = Field(default=None, max_length=50)
    notes: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0)
