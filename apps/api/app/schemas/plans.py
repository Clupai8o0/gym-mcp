"""Planned-set request/response schemas — the prescription, and how much of it was done.

A planned row and a logged row are deliberately different shapes. ``target_*`` names say these are
instructions, not measurements, so nothing downstream can mistake one for the other by reading a
field called ``reps`` and finding a number that describes an intention.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel
from app.schemas.exercises import ExerciseOut
from app.schemas.sets import LoggedSetOut, SetOut

if TYPE_CHECKING:
    from app.models import Exercise
    from app.services.plans import (
        Adherence,
        CompletedPlannedSet,
        PlannedItem,
        PlannedSession,
        SessionProgress,
    )


class PlannedSetOut(ORMModel):
    """One prescribed line, as stored."""

    id: uuid.UUID
    session_id: uuid.UUID
    exercise_id: uuid.UUID
    set_number: int
    order_index: int
    target_reps_min: int | None
    target_reps_max: int | None
    target_weight_kg: float | None
    target_rpe: float | None
    target_hold_seconds: int | None
    notes: str | None
    #: The logged set that satisfied this line, or ``null``. Present only while that set is live —
    #: deleting it reopens the line rather than leaving a link to something nobody can see.
    completed_set_id: uuid.UUID | None
    created_at: datetime


class PlannedItemOut(BaseModel):
    """A prescribed line with its movement and its completion state resolved."""

    planned: PlannedSetOut
    exercise: ExerciseOut | None
    is_completed: bool
    #: What was actually logged against it. ``null`` while the line is outstanding.
    completed_set: SetOut | None

    @classmethod
    def from_item(
        cls, item: PlannedItem, exercises: Mapping[uuid.UUID, Exercise]
    ) -> PlannedItemOut:
        exercise = exercises.get(item.planned.exercise_id)
        return cls(
            planned=PlannedSetOut.model_validate(item.planned),
            exercise=ExerciseOut.model_validate(exercise) if exercise is not None else None,
            is_completed=item.is_completed,
            completed_set=(
                SetOut.model_validate(item.completed_set)
                if item.completed_set is not None
                else None
            ),
        )


class PlannedSessionOut(BaseModel):
    """A session's whole prescription, in the order it is meant to be performed."""

    session_id: uuid.UUID
    performed_at: datetime
    title: str | None
    type: str | None
    planned_total: int
    completed_count: int
    items: list[PlannedItemOut]

    @classmethod
    def from_plan(cls, plan: PlannedSession) -> PlannedSessionOut:
        return cls(
            session_id=plan.session.id,
            performed_at=plan.session.performed_at,
            title=plan.session.title,
            type=plan.session.type,
            planned_total=plan.planned_total,
            completed_count=plan.completed_count,
            items=[PlannedItemOut.from_item(item, plan.exercises) for item in plan.items],
        )


class AdherenceOut(BaseModel):
    """How much of the prescription was done.

    ``percent`` is ``null`` when nothing was prescribed — neither 0 nor 100 is true of a session
    that had no plan, and both would read as a judgement about one.
    """

    planned_total: int
    completed_count: int
    pending_count: int
    off_plan_count: int
    percent: float | None

    @classmethod
    def from_adherence(cls, adherence: Adherence) -> AdherenceOut:
        return cls(
            planned_total=adherence.planned_total,
            completed_count=adherence.completed_count,
            pending_count=adherence.pending_count,
            off_plan_count=adherence.off_plan_count,
            percent=adherence.percent,
        )


class ExerciseProgressOut(BaseModel):
    """One movement's share of the prescription."""

    exercise: ExerciseOut
    planned: int
    completed: int
    remaining: int


class SessionProgressOut(BaseModel):
    """Planned vs done for one session, plus what to do next."""

    session_id: uuid.UUID
    adherence: AdherenceOut
    #: Every live set logged into the session, prescribed or not.
    logged_total: int
    exercises: list[ExerciseProgressOut]
    #: Just the movements with work outstanding — the same rows as ``exercises``, filtered.
    remaining_exercises: list[ExerciseProgressOut]
    #: The first outstanding line in the plan's own order, or ``null`` when the plan is complete
    #: (or there was never one).
    next_up: PlannedItemOut | None

    @classmethod
    def from_progress(cls, report: SessionProgress) -> SessionProgressOut:
        by_id = {row.exercise.id: row.exercise for row in report.exercises}
        breakdown = [
            ExerciseProgressOut(
                exercise=ExerciseOut.model_validate(row.exercise),
                planned=row.planned,
                completed=row.completed,
                remaining=row.remaining,
            )
            for row in report.exercises
        ]
        remaining = [row for row in breakdown if row.remaining > 0]
        return cls(
            session_id=report.session.id,
            adherence=AdherenceOut.from_adherence(report.adherence),
            logged_total=report.logged_total,
            exercises=breakdown,
            remaining_exercises=remaining,
            next_up=(
                PlannedItemOut.from_item(report.next_up, by_id)
                if report.next_up is not None
                else None
            ),
        )


class CompletedPlannedSetOut(BaseModel):
    """The line that was just satisfied, and the set that did it (with its PR verdict)."""

    planned: PlannedSetOut
    logged: LoggedSetOut

    @classmethod
    def from_completion(cls, completion: CompletedPlannedSet) -> CompletedPlannedSetOut:
        return cls(
            planned=PlannedSetOut.model_validate(completion.item.planned),
            logged=LoggedSetOut.from_logged(completion.logged),
        )


class PlannedSetCreate(BaseModel):
    """One line of a prescription. Every target is optional; a line with none is 'do a set'."""

    exercise_id: uuid.UUID
    set_number: int = Field(default=1, ge=1)
    #: Position in the workout. Omit and the lines are numbered in the order they arrive,
    #: continuing from whatever the session already holds.
    order_index: int | None = Field(default=None, ge=0)
    target_reps_min: int | None = Field(default=None, ge=0)
    target_reps_max: int | None = Field(default=None, ge=0)
    target_weight_kg: float | None = Field(default=None, ge=0)
    target_rpe: float | None = Field(default=None, ge=1, le=10)
    target_hold_seconds: int | None = Field(default=None, ge=0)
    notes: str | None = None
    #: Idempotency key: a repeat with the same key returns the original line.
    client_key: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _rep_range_counts_up(self) -> PlannedSetCreate:
        if (
            self.target_reps_min is not None
            and self.target_reps_max is not None
            and self.target_reps_max < self.target_reps_min
        ):
            raise ValueError("target_reps_max must be at least target_reps_min")
        return self


class PlannedSetsCreate(BaseModel):
    """Append lines to a session's prescription — all or nothing."""

    planned_sets: list[PlannedSetCreate] = Field(min_length=1, max_length=200)


class PlannedSessionCreate(PlannedSetsCreate):
    """Create a session and its prescription in one transaction."""

    performed_at: datetime
    title: str | None = Field(default=None, max_length=200)
    type: str | None = Field(default=None, max_length=50)
    notes: str | None = None
    client_key: str | None = Field(default=None, max_length=200)


class PlannedSetUpdate(BaseModel):
    """Patch one prescribed line; only supplied fields change.

    ``exercise_id`` and ``session_id`` are not here on purpose: moving a line to another movement
    or another day is not an edit of that line, it is a different line.
    """

    set_number: int | None = Field(default=None, ge=1)
    order_index: int | None = Field(default=None, ge=0)
    target_reps_min: int | None = Field(default=None, ge=0)
    target_reps_max: int | None = Field(default=None, ge=0)
    target_weight_kg: float | None = Field(default=None, ge=0)
    target_rpe: float | None = Field(default=None, ge=1, le=10)
    target_hold_seconds: int | None = Field(default=None, ge=0)
    notes: str | None = None
    clear_notes: bool = False


class PlannedSetComplete(BaseModel):
    """What was actually done against a prescribed line.

    Nothing is defaulted from the targets: a range of 8–10 has no single right answer, and a plan
    recording its own prescription as the result would make adherence a tautology.
    """

    weight_kg: float | None = Field(default=None, ge=0)
    reps: int | None = Field(default=None, ge=0)
    hold_seconds: int | None = Field(default=None, ge=0)
    rpe: float | None = Field(default=None, ge=1, le=10)
    notes: str | None = None
    is_backfill: bool = False
    client_key: str | None = Field(default=None, max_length=200)
