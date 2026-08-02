"""``workout_sessions`` — a logged training session (free ``title`` + optional ``type``)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk
from app.models.soft_delete import (
    client_key_col,
    client_key_index,
    deleted_at_col,
    deleted_at_index,
)


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"
    __table_args__ = (
        Index("workout_sessions_user_date_idx", "user_id", text("performed_at DESC")),
        Index("workout_sessions_type_idx", "user_id", "type"),
        client_key_index("workout_sessions"),
        deleted_at_index("workout_sessions"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str | None] = mapped_column(Text)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # NULL = never finished. This — not a date comparison — is what makes a session "active"
    # (services/sessions.get_active_session); `performed_at` is when it started, and a
    # server-side "is it today?" would evaluate in the server's timezone, not the lifter's.
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    #: Soft delete (docs/02 §Corrections). A deleted session's sets are deleted with it, and PRs
    #: for every exercise it touched are recalculated — the row leaves the data, not just the list.
    deleted_at: Mapped[datetime | None] = deleted_at_col()
    #: Caller-supplied idempotency key; a repeat `log_session` with the same key returns this row.
    client_key: Mapped[str | None] = client_key_col()
    created_at: Mapped[datetime] = created_at_col()
