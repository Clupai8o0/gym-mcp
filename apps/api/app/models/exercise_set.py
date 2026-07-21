"""``exercise_sets`` — one logged set, referencing a catalog ``exercise_id``.

``user_id`` is denormalized (also on the parent session) for fast per-user queries and
PR detection without a join back through ``workout_sessions``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk


class ExerciseSet(Base):
    __tablename__ = "exercise_sets"
    __table_args__ = (
        CheckConstraint("rpe is null or (rpe >= 1 and rpe <= 10)", name="rpe"),
        CheckConstraint(
            "pr_type in ('weight','reps','hold_time','first_log') or pr_type is null",
            name="pr_type",
        ),
        Index("exercise_sets_session_idx", "session_id"),
        Index("exercise_sets_user_exercise_idx", "user_id", "exercise_id"),
        Index("exercise_sets_pr_idx", "user_id", "exercise_id", "is_pr"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric)
    reps: Mapped[int | None] = mapped_column(Integer)
    hold_seconds: Mapped[int | None] = mapped_column(Integer)
    rpe: Mapped[Decimal | None] = mapped_column(Numeric)
    is_pr: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    pr_type: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
