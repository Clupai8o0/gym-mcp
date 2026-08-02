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
from app.models.soft_delete import (
    client_key_col,
    client_key_index,
    deleted_at_col,
    deleted_at_index,
)


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
        client_key_index("exercise_sets"),
        deleted_at_index("exercise_sets"),
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
    #: Historical data entered after the fact, not performed-and-measured. A backfilled set is
    #: still training you did, so it counts toward volume and frequency — but it is excluded from
    #: PR detection, because a placeholder `reps=1` used to register as a reps PR of 1.
    is_backfill: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    #: Soft delete. A deleted set stops contributing to PR detection immediately (the recompute
    #: skips it), which is what makes "delete the set that set the record" fall back correctly.
    deleted_at: Mapped[datetime | None] = deleted_at_col()
    #: Caller-supplied idempotency key; a repeat `log_set` with the same key returns this row.
    client_key: Mapped[str | None] = client_key_col()
    created_at: Mapped[datetime] = created_at_col()
