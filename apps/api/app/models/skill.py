"""Skills module (secondary): ``skills`` catalog + per-user ``skill_progress``."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, updated_at_col, uuid_pk


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    total_stages: Mapped[int] = mapped_column(Integer, nullable=False)
    stages: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    related_exercise_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("exercises.id"))
    created_at: Mapped[datetime] = created_at_col()


class SkillProgress(Base):
    __tablename__ = "skill_progress"
    __table_args__ = (
        CheckConstraint("progress_percent between 0 and 100", name="progress_percent"),
        UniqueConstraint("user_id", "skill_id", name="skill_progress_uidx"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    current_stage: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    stage_name: Mapped[str | None] = mapped_column(Text)
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = updated_at_col()
