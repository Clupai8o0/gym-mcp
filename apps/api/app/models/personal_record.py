"""``personal_records`` — one row per (user, exercise, metric); upserted by PR detection."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk


class PersonalRecord(Base):
    __tablename__ = "personal_records"
    __table_args__ = (
        CheckConstraint("pr_type in ('weight','reps','hold_time')", name="pr_type"),
        UniqueConstraint("user_id", "exercise_id", "pr_type", name="personal_records_uidx"),
        Index("personal_records_user_idx", "user_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    pr_type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    achieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
