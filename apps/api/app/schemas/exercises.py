"""Exercise request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel, PageMeta


class ExerciseOut(ORMModel):
    """Catalog summary (list rows + nested group headers)."""

    id: uuid.UUID
    slug: str
    name: str
    category: str | None
    force: str | None
    level: str | None
    mechanic: str | None
    equipment: str | None
    primary_muscles: list[str]
    secondary_muscles: list[str]
    illustration_url: str | None
    illustration_status: str
    # Read for the derivation below, but not serialized (internal owner id).
    created_by_user_id: uuid.UUID | None = Field(default=None, exclude=True)
    is_custom: bool = False

    @model_validator(mode="after")
    def _derive_is_custom(self) -> ExerciseOut:
        self.is_custom = self.created_by_user_id is not None
        return self


class ExerciseDetailOut(ExerciseOut):
    """Full detail: adds the how-to steps + provenance/timestamps."""

    instructions: list[str]
    source: str
    created_at: datetime
    updated_at: datetime


class ExerciseListOut(PageMeta):
    items: list[ExerciseOut]


class ExerciseCreate(BaseModel):
    """Create a custom exercise. ``slug`` is derived from ``name`` when omitted."""

    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=200)
    category: str | None = None
    force: str | None = None
    level: str | None = None
    mechanic: str | None = None
    equipment: str | None = None
    primary_muscles: list[str] = Field(default_factory=list)
    secondary_muscles: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
