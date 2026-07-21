"""``workout_sessions`` — a logged training session (free ``title`` + optional ``type``)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"
    __table_args__ = (
        Index("workout_sessions_user_date_idx", "user_id", text("performed_at DESC")),
        Index("workout_sessions_type_idx", "user_id", "type"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str | None] = mapped_column(Text)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_col()
