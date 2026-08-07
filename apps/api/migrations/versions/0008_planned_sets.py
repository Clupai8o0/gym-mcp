"""planned_sets — the prescription layer, kept out of every derived number (docs/02 §Planning).

Until now a session could only hold sets that had already happened, so a coach-written plan had
nowhere to live in the app. This migration adds ``planned_sets``: what a session is *meant* to
contain, alongside — never inside — what it actually did.

**One new table, nothing altered.** No column is added to ``exercise_sets`` and no query changes,
which is the point. Volume, tonnage, frequency and PR detection read ``exercise_sets`` and nothing
else; a prescription stored in its own table cannot reach them, so there is no exclusion flag for
six aggregate queries to remember. The alternative — an ``is_planned`` boolean on ``exercise_sets``
— would have made every one of those queries responsible for the invariant, and the first one that
forgot would credit a lifter with work they were only told to do.

A planned row reaches the numbers exactly once, through ``services/plans.complete``, which writes a
real ``exercise_sets`` row (normal PR detection and all) and records its id in
``completed_set_id``. That column is a **label on the plan**, never an input to anything derived.

Three details in the DDL carry decisions that are easy to lose:

* ``completed_set_id`` is ``on delete set null``, not cascade. Deleting a plan line must never
  delete the set it recorded — the training happened whatever the plan says — and ``purge_deleted``
  has to be able to free a set's storage without tripping over the row that named it.
* ``planned_sets_completed_set_uidx`` is unique. One logged set can satisfy at most one prescribed
  row; without it two planned rows could both claim the same set and a session would report more
  work completed than was ever logged.
* ``order_index`` is separate from ``set_number`` because ``set_number`` cannot order a
  prescription that alternates movements: a superset is A1, B1, A2, B2, and each of those is set 1
  or set 2 *of its own exercise*.

``deleted_at`` + ``client_key`` follow the conventions ``0007_corrections`` established, so the
planning tools inherit soft delete, ``restore`` and retry-idempotency without a second mechanism.

Revision ID: 0008_planned_sets
Revises: 0007_corrections
Create Date: 2026-08-06 10:40:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_planned_sets"
down_revision: str | None = "0007_corrections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planned_sets",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workout_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "exercise_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exercises.id"),
            nullable=False,
        ),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("target_reps_min", sa.Integer(), nullable=True),
        sa.Column("target_reps_max", sa.Integer(), nullable=True),
        sa.Column("target_weight_kg", sa.Numeric(), nullable=True),
        sa.Column("target_rpe", sa.Numeric(), nullable=True),
        sa.Column("target_hold_seconds", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "completed_set_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exercise_sets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_key", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Bare names, as on `exercise_sets`: the metadata naming convention
        # (`%(table_name)s_%(constraint_name)s_check`) supplies the table prefix and the suffix.
        # Spelling the full name here produces `planned_sets_planned_sets_target_rpe_check_check`
        # in the shipped database — which `alembic check` does not compare, so it would have
        # drifted from the model silently and forever.
        sa.CheckConstraint(
            "target_rpe is null or (target_rpe >= 1 and target_rpe <= 10)",
            name="target_rpe",
        ),
        sa.CheckConstraint(
            "target_reps_min is null or target_reps_max is null "
            "or target_reps_max >= target_reps_min",
            name="reps_range",
        ),
    )

    # The read order of a prescription: by position in the workout, then by set within a movement.
    op.create_index(
        "planned_sets_session_idx", "planned_sets", ["session_id", "order_index", "set_number"]
    )
    op.create_index("planned_sets_user_exercise_idx", "planned_sets", ["user_id", "exercise_id"])
    # Live rows only. A deleted line is not part of the plan any more, so its claim on a set must
    # not survive it — otherwise deleting a completed line and then completing another against the
    # same set trips the index instead of the service's own conflict check, and a domain refusal
    # becomes a 500. The predicate matches `plans._claimant` exactly, which is the point.
    op.create_index(
        "planned_sets_completed_set_uidx",
        "planned_sets",
        ["completed_set_id"],
        unique=True,
        postgresql_where=sa.text("completed_set_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "planned_sets_client_key_uidx",
        "planned_sets",
        ["user_id", "client_key"],
        unique=True,
        postgresql_where=sa.text("client_key IS NOT NULL"),
    )
    op.create_index(
        "planned_sets_deleted_at_idx",
        "planned_sets",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("planned_sets_deleted_at_idx", table_name="planned_sets")
    op.drop_index("planned_sets_client_key_uidx", table_name="planned_sets")
    op.drop_index("planned_sets_completed_set_uidx", table_name="planned_sets")
    op.drop_index("planned_sets_user_exercise_idx", table_name="planned_sets")
    op.drop_index("planned_sets_session_idx", table_name="planned_sets")
    op.drop_table("planned_sets")
