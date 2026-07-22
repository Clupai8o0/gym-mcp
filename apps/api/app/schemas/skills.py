"""Skills module response/request schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

if TYPE_CHECKING:
    from app.services.skills import SkillWithProgress


class SkillProgressOut(ORMModel):
    current_stage: int
    stage_name: str | None
    progress_percent: int
    notes: str | None
    updated_at: datetime


class SkillOverviewItem(BaseModel):
    """A skill flattened with the user's progress (defaults when not started)."""

    slug: str
    name: str
    total_stages: int
    current_stage: int
    stage_name: str | None
    progress_percent: int
    notes: str | None
    updated_at: datetime | None

    @classmethod
    def from_pair(cls, pair: SkillWithProgress) -> SkillOverviewItem:
        p = pair.progress
        return cls(
            slug=pair.skill.slug,
            name=pair.skill.name,
            total_stages=pair.skill.total_stages,
            current_stage=p.current_stage if p else 0,
            stage_name=p.stage_name if p else None,
            progress_percent=p.progress_percent if p else 0,
            notes=p.notes if p else None,
            updated_at=p.updated_at if p else None,
        )


class SkillsOverviewOut(BaseModel):
    items: list[SkillOverviewItem]


class SkillDetailOut(BaseModel):
    slug: str
    name: str
    total_stages: int
    stages: list[dict[str, Any]] | None
    related_exercise_id: uuid.UUID | None
    progress: SkillProgressOut | None

    @classmethod
    def from_pair(cls, pair: SkillWithProgress) -> SkillDetailOut:
        return cls(
            slug=pair.skill.slug,
            name=pair.skill.name,
            total_stages=pair.skill.total_stages,
            stages=pair.skill.stages,
            related_exercise_id=pair.skill.related_exercise_id,
            progress=(SkillProgressOut.model_validate(pair.progress) if pair.progress else None),
        )


class SkillProgressUpsert(BaseModel):
    current_stage: int = Field(ge=0)
    progress_percent: int = Field(ge=0, le=100)
    stage_name: str | None = Field(default=None, max_length=100)
    notes: str | None = None
