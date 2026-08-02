"""manual PRs — ``personal_records.source`` + the ``personal_records_history`` log (docs/02).

Until now a personal record could only be born inside ``log_set``: detection ran over the logged
sets and upserted the best. That cannot express an **estimated 1RM**, a **hold timed outside a
session**, or a **record migrated from another app** — none of which have a set to derive from.

Two additions:

* ``personal_records.source`` — ``'auto'`` (derived from a set) or ``'manual'`` (the user said
  so). Existing rows are all auto by definition, which is exactly what the server default gives
  them, so the backfill is a no-op by construction rather than an UPDATE.
* ``personal_records_history`` — append-only, one row per accepted PR write. It replaces the old
  read path for PR history, which scanned ``exercise_sets`` for ``is_pr`` and therefore could
  never show a manual entry.

The history table is **backfilled from those same ``is_pr`` sets**, so the chronology every
existing user already sees is preserved exactly; only its source changes. The backfill mirrors
``services/sets._concrete_metric``: a set flagged ``'first_log'`` is collapsed to weight, then
reps, then hold_time — whichever it actually carries.

Revision ID: 0006_manual_prs
Revises: 0005_illustration_light_variant
Create Date: 2026-08-02 13:30:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_manual_prs"
down_revision: str | None = "0005_illustration_light_variant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── personal_records.source ──────────────────────────────────────────────────────────
    # NOT NULL with a server default: every existing row is auto-detected by definition, so the
    # default *is* the backfill and no UPDATE pass is needed.
    op.add_column(
        "personal_records",
        sa.Column("source", sa.Text(), nullable=False, server_default="auto"),
    )
    op.create_check_constraint(
        "personal_records_source_check", "personal_records", "source in ('auto','manual')"
    )

    # ── personal_records_history ─────────────────────────────────────────────────────────
    op.create_table(
        "personal_records_history",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exercise_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pr_type", sa.Text(), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("set_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "pr_type in ('weight','reps','hold_time')",
            name="personal_records_history_pr_type_check",
        ),
        sa.CheckConstraint(
            "source in ('auto','manual')", name="personal_records_history_source_check"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="personal_records_history_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["exercises.id"], name="personal_records_history_exercise_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["set_id"],
            ["exercise_sets.id"],
            name="personal_records_history_set_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["workout_sessions.id"],
            name="personal_records_history_session_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="personal_records_history_pkey"),
    )
    op.create_index(
        "personal_records_history_lookup_idx",
        "personal_records_history",
        ["user_id", "exercise_id", "pr_type", "achieved_at"],
    )
    # Auto rows are rebuilt wholesale on every set write; this makes a double-run impossible.
    op.create_index(
        "personal_records_history_set_uidx",
        "personal_records_history",
        ["set_id", "pr_type"],
        unique=True,
        postgresql_where=sa.text("set_id IS NOT NULL"),
    )

    # ── backfill the chronology from the sets that already carry it ──────────────────────
    # `pr_type = 'first_log'` is a set-level marker, not a metric; collapse it the same way
    # `services/sets._concrete_metric` does. Sets whose flagged metric has no value are skipped
    # rather than written as NULL — there is nothing meaningful to record.
    op.execute("""
        INSERT INTO personal_records_history
            (user_id, exercise_id, pr_type, value, unit, achieved_at, source, set_id, session_id)
        SELECT
            s.user_id,
            s.exercise_id,
            m.metric,
            CASE m.metric
                WHEN 'weight'    THEN s.weight_kg
                WHEN 'reps'      THEN s.reps::numeric
                WHEN 'hold_time' THEN s.hold_seconds::numeric
            END AS value,
            CASE m.metric
                WHEN 'weight'    THEN 'kg'
                WHEN 'reps'      THEN 'reps'
                WHEN 'hold_time' THEN 's'
            END AS unit,
            ws.performed_at,
            'auto',
            s.id,
            s.session_id
        FROM exercise_sets s
        JOIN workout_sessions ws ON ws.id = s.session_id
        CROSS JOIN LATERAL (
            SELECT CASE
                WHEN s.pr_type <> 'first_log' THEN s.pr_type
                WHEN s.weight_kg    IS NOT NULL THEN 'weight'
                WHEN s.reps         IS NOT NULL THEN 'reps'
                ELSE 'hold_time'
            END AS metric
        ) m
        WHERE s.is_pr IS TRUE
          AND s.pr_type IS NOT NULL
          AND CASE m.metric
                WHEN 'weight'    THEN s.weight_kg
                WHEN 'reps'      THEN s.reps::numeric
                WHEN 'hold_time' THEN s.hold_seconds::numeric
              END IS NOT NULL
        ON CONFLICT DO NOTHING
        """)


def downgrade() -> None:
    op.drop_table("personal_records_history")
    op.drop_constraint("personal_records_source_check", "personal_records", type_="check")
    op.drop_column("personal_records", "source")
