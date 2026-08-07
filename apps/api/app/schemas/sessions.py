"""Workout-session request/response schemas (detail groups sets by exercise)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel, PageMeta
from app.schemas.exercises import ExerciseOut
from app.schemas.plans import AdherenceOut
from app.schemas.sets import LoggedSetOut, SetCreate, SetOut

if TYPE_CHECKING:
    from app.services.sessions import FinishedSession, SessionDetail


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

    ``set_count`` lives here and **not** on :class:`SessionOut`, which is validated straight
    off raw ORM rows at every other call site and would raise on a required field with no
    matching attribute. It is here because it is what the callers of this endpoint actually
    need next: both the docked session bar and the home workout card say "N sets" and would
    otherwise fetch the entire session detail — every set plus full exercise rows — to count.
    """

    session: SessionOut | None
    #: Sets logged into the active session so far; ``0`` when there is no active session.
    #: Required, not defaulted — the response always carries it, and a client that has to
    #: cope with it being absent would need a fallback that can never fire.
    set_count: int
    #: Lines in this session's prescription; ``0`` on an ordinary unplanned workout. A session
    #: that exists with a plan and nothing logged yet is still the active session, and this is
    #: what tells a client there is something to work through.
    planned_total: int = 0
    #: How many of those lines have been completed. Not the same as ``set_count``, which counts
    #: everything logged including work nobody prescribed.
    completed_count: int = 0


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
    #: Idempotency key: a repeat with the same key returns the original session.
    client_key: str | None = Field(default=None, max_length=200)


class SessionWithSetsCreate(SessionCreate):
    """Create a session and its sets in one transaction (all or nothing)."""

    sets: list[SetCreate] = Field(min_length=1, max_length=200)


class SessionWithSetsOut(BaseModel):
    session: SessionOut
    sets: list[LoggedSetOut]


class SessionUpdate(BaseModel):
    """Patch session metadata; only supplied fields change.

    ``clear_notes`` rather than a nullable ``notes``: in a partial update ``null`` already means
    "leave alone", so emptying a field needs its own word.
    """

    performed_at: datetime | None = None
    ended_at: datetime | None = None
    title: str | None = Field(default=None, max_length=200)
    type: str | None = Field(default=None, max_length=50)
    notes: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0)
    clear_notes: bool = False


class FinishedSessionOut(SessionOut):
    """A closed session, plus how much of its prescription it covered.

    Widening the finished session rather than wrapping it: the one field the UI reads off this
    response is ``duration_minutes``, and every other caller treats it as a session. ``adherence``
    is additive, so nothing that worked before has to change to keep working.
    """

    adherence: AdherenceOut

    @classmethod
    def from_finished(cls, finished: FinishedSession) -> FinishedSessionOut:
        base = SessionOut.model_validate(finished.session)
        return cls(
            **base.model_dump(),
            adherence=AdherenceOut.from_adherence(finished.adherence),
        )


class SessionDeleteOut(BaseModel):
    """What a delete did — or, with ``dry_run``, would have done."""

    session: SessionOut
    set_count: int
    exercises_recalculated: int
    dry_run: bool
    #: Prescribed lines removed with the session. They go unconditionally — a plan cannot outlive
    #: the workout it prescribes — so this is a report, not a decision.
    planned_count: int = 0
