"""corrections — soft delete, idempotency keys, slug aliases, backfill flag (docs/02 §Corrections).

Tempo was append-only in practice: every write was permanent. Three concrete cases proved the
write path was only half built — a bug wrote ``duration_minutes = 136070`` with no way to correct
the stored value, a bogus 60 kg ``personal_records_history`` row could not be removed, and a typo
in a custom exercise's name would have been forever. This migration is the storage half of the
correction tooling.

Everything here is **additive and nullable**, so it is a metadata-only change on Postgres — no
table rewrite, no backfill, and every existing row means exactly what it meant before:

* ``deleted_at`` on ``workout_sessions``, ``exercise_sets``, ``exercises`` and
  ``personal_records_history``. ``NULL`` = live, which is what every existing row already is.
  Reads exclude non-NULL by default; ``services/corrections.restore`` clears it again.
  Deliberately **not** on ``personal_records``: that table is fully derived by the recompute, and
  a soft-deleted row would still occupy its ``(user, exercise, pr_type)`` unique slot, so the next
  recalculation would find a row it must neither update nor duplicate. Deleting a record is
  expressed as deleting the history entries that support it, then recalculating.
* ``client_key`` on ``workout_sessions``, ``exercise_sets`` and ``personal_records_history``, with
  a partial unique index per user. A retried write that never got its answer back returns the
  original row instead of creating a second one — the failure that left two identical
  ``upper_hypertrophy`` sessions dated 1 May.
* ``personal_records_history.counted`` — did this entry actually set a record? ``auto`` rows are
  derived output and are only written when they count; ``manual`` rows are **input**, so a claim
  that never beat the running best at its own moment stays in the table (as a floor the replay can
  reuse if the set that outranked it is later deleted) but leaves the chronology. Without it,
  history cannot promise to be monotonic under arbitrary edits.
* ``exercise_sets.is_backfill`` — historical data entered after the fact. It still counts toward
  volume and frequency (it is training that happened) but is excluded from PR detection, because a
  placeholder ``reps=1`` used to register as a reps PR of 1.
* ``exercise_slug_aliases`` — renaming a custom exercise regenerates its slug, and a slug is a
  public identifier. The old one keeps resolving.

The index predicates match the live-slug indexes exactly, so an alias can never introduce an
ambiguity a real slug could not.

Revision ID: 0007_corrections
Revises: 0006_manual_prs
Create Date: 2026-08-02 15:10:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_corrections"
down_revision: str | None = "0006_manual_prs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Tables gaining ``deleted_at``. See the module docstring for why `personal_records` is absent.
_SOFT_DELETE_TABLES = (
    "workout_sessions",
    "exercise_sets",
    "exercises",
    "personal_records_history",
)

#: Tables gaining ``client_key`` + its partial unique index (all are user-scoped).
_IDEMPOTENT_TABLES = ("workout_sessions", "exercise_sets", "personal_records_history")


def upgrade() -> None:
    for table in _SOFT_DELETE_TABLES:
        op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        # Partial: the overwhelming majority of rows are live, and every read filters on
        # `deleted_at IS NULL`, so indexing the deleted minority is what the purge path needs.
        op.create_index(
            f"{table}_deleted_at_idx",
            table,
            ["deleted_at"],
            postgresql_where=sa.text("deleted_at IS NOT NULL"),
        )

    for table in _IDEMPOTENT_TABLES:
        op.add_column(table, sa.Column("client_key", sa.Text(), nullable=True))
        op.create_index(
            f"{table}_client_key_uidx",
            table,
            ["user_id", "client_key"],
            unique=True,
            postgresql_where=sa.text("client_key IS NOT NULL"),
        )

    op.add_column(
        "exercise_sets",
        sa.Column("is_backfill", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # Existing rows all counted — `auto` rows were only ever written when they set a record, and
    # `manual` rows were unconditionally accepted — so the server default *is* the backfill.
    op.add_column(
        "personal_records_history",
        sa.Column("counted", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "exercise_slug_aliases",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "exercise_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exercises.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "exercise_slug_aliases_global_uidx",
        "exercise_slug_aliases",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("created_by_user_id IS NULL"),
    )
    op.create_index(
        "exercise_slug_aliases_custom_uidx",
        "exercise_slug_aliases",
        ["created_by_user_id", "slug"],
        unique=True,
        postgresql_where=sa.text("created_by_user_id IS NOT NULL"),
    )
    op.create_index("exercise_slug_aliases_exercise_idx", "exercise_slug_aliases", ["exercise_id"])


def downgrade() -> None:
    op.drop_index("exercise_slug_aliases_exercise_idx", table_name="exercise_slug_aliases")
    op.drop_index("exercise_slug_aliases_custom_uidx", table_name="exercise_slug_aliases")
    op.drop_index("exercise_slug_aliases_global_uidx", table_name="exercise_slug_aliases")
    op.drop_table("exercise_slug_aliases")

    op.drop_column("personal_records_history", "counted")
    op.drop_column("exercise_sets", "is_backfill")

    for table in _IDEMPOTENT_TABLES:
        op.drop_index(f"{table}_client_key_uidx", table_name=table)
        op.drop_column(table, "client_key")

    for table in _SOFT_DELETE_TABLES:
        op.drop_index(f"{table}_deleted_at_idx", table_name=table)
        op.drop_column(table, "deleted_at")
