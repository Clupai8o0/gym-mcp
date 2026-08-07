"""``planned_sets`` — the prescription: what a session is *meant* to contain.

A logged set is a fact about what happened. A planned set is an instruction about what should.
Keeping them in **separate tables** is the entire design, and it is not a stylistic preference:
volume, tonnage, frequency and PR detection all read ``exercise_sets`` and nothing else, so a
prescription cannot inflate a total however it is written. The alternative — one table with a
``is_planned`` flag — would put the burden on six aggregate queries to remember to exclude it, and
the first one that forgot would quietly credit a lifter with work they were only told to do.

A planned row reaches the numbers exactly once, and only through the front door:
``services/plans.complete`` writes a real ``exercise_sets`` row (normal PR detection and all) and
records its id in :attr:`PlannedSet.completed_set_id`. The link is a *label on the plan*, never an
input to anything derived.

**Completion is read through the link, not from it.** ``completed_set_id`` pointing somewhere is
not enough — the set it points at has to still be live. That is what makes deleting the set you
logged against a prescription put the prescribed row back to pending, with no second write and no
chance of the two disagreeing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, uuid_pk
from app.models.soft_delete import (
    client_key_col,
    client_key_index,
    deleted_at_col,
    deleted_at_index,
)


class PlannedSet(Base):
    __tablename__ = "planned_sets"
    __table_args__ = (
        CheckConstraint(
            "target_rpe is null or (target_rpe >= 1 and target_rpe <= 10)", name="target_rpe"
        ),
        CheckConstraint(
            "target_reps_min is null or target_reps_max is null "
            "or target_reps_max >= target_reps_min",
            name="reps_range",
        ),
        Index("planned_sets_session_idx", "session_id", "order_index", "set_number"),
        Index("planned_sets_user_exercise_idx", "user_id", "exercise_id"),
        # One logged set can satisfy at most one **live** prescribed row. Without the uniqueness,
        # two rows could both claim a set and a session would report more work completed than was
        # ever logged; without the ``deleted_at`` half of the predicate, a *deleted* line would
        # keep holding the slot, and the index — not the service's own conflict check — would be
        # what refused the next completion, turning a domain error into a 500. The predicate is
        # deliberately identical to the filter in ``plans._claimant``.
        Index(
            "planned_sets_completed_set_uidx",
            "completed_set_id",
            unique=True,
            postgresql_where=text("completed_set_id IS NOT NULL AND deleted_at IS NULL"),
        ),
        client_key_index("planned_sets"),
        deleted_at_index("planned_sets"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    #: Denormalized from the parent session, exactly as on ``exercise_sets`` — it is what scopes
    #: every read, and what the generic ``corrections`` restore/purge path expects to find.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    #: Which set of that exercise this is (1-based) — handed straight to the logged set on
    #: completion, so the prescription and the log agree on numbering without a second decision.
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Position in the workout as a whole. ``set_number`` cannot order a prescription that
    #: alternates movements: a superset is A1, B1, A2, B2, and every one of those is "set 1" or
    #: "set 2" of its own exercise.
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    #: A rep target as a range. Both ends equal is a fixed number ("5 reps"); only a min is "at
    #: least"; only a max is "up to"; neither is a set with no rep target at all — an AMRAP, or a
    #: movement prescribed on load or time instead.
    target_reps_min: Mapped[int | None] = mapped_column(Integer)
    target_reps_max: Mapped[int | None] = mapped_column(Integer)
    target_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric)
    target_rpe: Mapped[Decimal | None] = mapped_column(Numeric)
    target_hold_seconds: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    #: The logged set that satisfied this prescription, if one has. ``SET NULL`` on delete so
    #: ``purge_deleted`` can free a set's storage without tripping over the plan that named it.
    completed_set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exercise_sets.id", ondelete="SET NULL")
    )
    #: Soft delete. Removing a line from a plan is a correction like any other, and ``restore``
    #: puts it back — a prescription deleted by mistake is not recoverable from the log, because
    #: the log never held it.
    deleted_at: Mapped[datetime | None] = deleted_at_col()
    #: Caller-supplied idempotency key; a repeat write with the same key returns this row.
    client_key: Mapped[str | None] = client_key_col()
    created_at: Mapped[datetime] = created_at_col()
