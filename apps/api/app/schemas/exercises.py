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
    # The light-theme twin of ``illustration_url`` (same art, inverted linework, same accent).
    # Non-NULL whenever ``illustration_url`` is; the client picks per active theme (docs/06).
    illustration_url_light: str | None
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


class ExerciseUpdate(BaseModel):
    """Patch a **custom** exercise; only supplied fields change.

    No ``slug``: it is derived from ``name``, so the two cannot drift. Renaming keeps the old slug
    resolvable as an alias.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = None
    force: str | None = None
    level: str | None = None
    mechanic: str | None = None
    equipment: str | None = None
    primary_muscles: list[str] | None = None
    secondary_muscles: list[str] | None = None
    instructions: list[str] | None = None


class ExerciseDeleteOut(BaseModel):
    """What a custom-exercise delete did — or, with ``dry_run``, would have done."""

    exercise: ExerciseOut
    set_count: int
    reassigned_to: ExerciseOut | None
    dry_run: bool
    #: Prescribed lines naming this exercise; they block the delete exactly as sets do.
    planned_count: int = 0
