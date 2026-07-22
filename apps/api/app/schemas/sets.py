"""Set request/response schemas, including the PR verdict returned on log/update."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

if TYPE_CHECKING:
    from app.services.sets import LoggedSet


class SetOut(ORMModel):
    id: uuid.UUID
    session_id: uuid.UUID
    exercise_id: uuid.UUID
    set_number: int
    weight_kg: float | None
    reps: int | None
    hold_seconds: int | None
    rpe: float | None
    is_pr: bool
    pr_type: str | None
    notes: str | None
    created_at: datetime


class PrInfo(BaseModel):
    """The PR verdict for the set that was just logged/updated."""

    is_pr: bool
    pr_type: str | None
    previous_best: float | None
    new_value: float | None


class LoggedSetOut(BaseModel):
    set: SetOut
    pr: PrInfo

    @classmethod
    def from_logged(cls, logged: LoggedSet) -> LoggedSetOut:
        return cls(
            set=SetOut.model_validate(logged.set),
            pr=PrInfo(
                is_pr=logged.pr.is_pr,
                pr_type=logged.pr.pr_type,
                previous_best=(
                    float(logged.pr.previous_best) if logged.pr.previous_best is not None else None
                ),
                new_value=(float(logged.pr.new_value) if logged.pr.new_value is not None else None),
            ),
        )


class SetCreate(BaseModel):
    """Log a set within a session (the session id comes from the path)."""

    exercise_id: uuid.UUID
    set_number: int = Field(ge=1)
    weight_kg: float | None = Field(default=None, ge=0)
    reps: int | None = Field(default=None, ge=0)
    hold_seconds: int | None = Field(default=None, ge=0)
    rpe: float | None = Field(default=None, ge=1, le=10)
    notes: str | None = None


class SetUpdate(BaseModel):
    """Patch a set's metrics; only supplied fields change (PR is recomputed)."""

    set_number: int | None = Field(default=None, ge=1)
    weight_kg: float | None = Field(default=None, ge=0)
    reps: int | None = Field(default=None, ge=0)
    hold_seconds: int | None = Field(default=None, ge=0)
    rpe: float | None = Field(default=None, ge=1, le=10)
    notes: str | None = None
