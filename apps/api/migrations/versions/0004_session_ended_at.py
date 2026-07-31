"""session lifecycle — ``workout_sessions.ended_at`` (docs/02, Phase 11A).

A session had no end: "is a workout in progress?" was answered by comparing
``performed_at`` to today's date, which evaluates in the *server's* timezone (UTC in
production) and can never reopen yesterday's work. ``ended_at`` makes the lifecycle
explicit — NULL means "still open".

Purely additive and reversible. **No backfill:** existing rows read as never-finished,
which is correct — they were logged before the app could finish anything. The read-time
staleness rule in ``services/sessions.get_active_session`` retires them on first read,
stamping ``ended_at`` from their last set (Decision Log D31).

Revision ID: 0004_session_ended_at
Revises: 0003_oauth
Create Date: 2026-07-31 09:10:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_session_ended_at"
down_revision: str | None = "0003_oauth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workout_sessions",
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workout_sessions", "ended_at")
