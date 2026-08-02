"""``personal_records`` — the current best per (user, exercise, metric) — and its append-only log.

Two tables, two jobs:

* :class:`PersonalRecord` answers *"what is my best?"*. One row per
  ``(user_id, exercise_id, pr_type)``, upserted by PR detection in ``services/sets`` or written
  outright by ``services/prs.log_manual_pr``. ``source`` records which of the two put it there.
* :class:`PersonalRecordHistory` answers *"how did I get here?"*. One row per accepted PR write,
  read chronologically by ``services/prs.history``.

The history table exists because the old answer — scanning ``exercise_sets`` for ``is_pr`` — can
only ever see records that came from a logged set. An estimated 1RM, a hold timed outside a
session, or a record migrated from another app has no set to flag, so it was invisible.
"""

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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk

#: The concrete record metrics. ``exercise_sets.pr_type`` may also hold ``'first_log'``, which
#: ``services/sets._concrete_metric`` collapses into one of these before a record is written.
PR_TYPES: tuple[str, ...] = ("weight", "reps", "hold_time")

#: The unit each metric is stored in. Weights are kg everywhere; display conversion is the web's
#: job (``users.unit_pref``), never the database's.
PR_UNITS: dict[str, str] = {"weight": "kg", "reps": "reps", "hold_time": "s"}

#: Who wrote the record. ``auto`` = derived from a logged set; ``manual`` = the user said so.
PR_SOURCES: tuple[str, ...] = ("auto", "manual")

_PR_TYPE_SQL = ", ".join(f"'{t}'" for t in PR_TYPES)
_PR_SOURCE_SQL = ", ".join(f"'{s}'" for s in PR_SOURCES)


class PersonalRecord(Base):
    __tablename__ = "personal_records"
    __table_args__ = (
        CheckConstraint(f"pr_type in ({_PR_TYPE_SQL})", name="pr_type"),
        CheckConstraint(f"source in ({_PR_SOURCE_SQL})", name="source"),
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
    #: ``manual`` rows are protected from PR detection unless a logged set strictly beats them
    #: (``services/sets._sync_records``) — a user's explicit correction is not guesswork.
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="auto")


class PersonalRecordHistory(Base):
    """One row per accepted PR write — the chronology behind the current best.

    ``auto`` rows are **derived**: ``services/sets._recompute`` rebuilds them wholesale for an
    exercise on every set write, which is what keeps them honest when a set is edited or deleted.
    ``manual`` rows are **append-only** — nothing but the user deletes them, so re-stating a PR
    leaves both entries visible.
    """

    __tablename__ = "personal_records_history"
    __table_args__ = (
        CheckConstraint(f"pr_type in ({_PR_TYPE_SQL})", name="pr_type"),
        CheckConstraint(f"source in ({_PR_SOURCE_SQL})", name="source"),
        # The read path: one exercise + metric, oldest first.
        Index(
            "personal_records_history_lookup_idx",
            "user_id",
            "exercise_id",
            "pr_type",
            "achieved_at",
        ),
        # Belt and braces on the auto rebuild: a set can back at most one record per metric, so a
        # rebuild that somehow ran twice cannot double up.
        Index(
            "personal_records_history_set_uidx",
            "set_id",
            "pr_type",
            unique=True,
            postgresql_where=text("set_id IS NOT NULL"),
        ),
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
    source: Mapped[str] = mapped_column(Text, nullable=False)
    #: The set that earned an ``auto`` entry; NULL for ``manual`` ones (there is no set).
    set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exercise_sets.id", ondelete="CASCADE")
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
