"""illustrations — ``exercises.illustration_url_light`` (docs/02, docs/06, Phase 4).

The locked style (STYLE_VERSION 3) is off-white line art with an amber working-muscle accent.
Off-white is unreadable on a light surface, and CSS cannot fix it at render time: ``filter:
invert()`` cannot act selectively and would drag the amber accent to blue. So each illustration
ships as a pair — the generated dark asset plus a light twin whose achromatic linework is
inverted and whose accent is byte-identical (``app/images/chroma.invert_neutral``).

The twin is derived locally from the same generation, so the pair costs one model call, and both
blobs are written in the same step: this column is non-NULL exactly when ``illustration_url`` is.

Purely additive and reversible. **No backfill:** any pre-existing art predates the accent style
and is stale anyway — those rows are reset to ``pending`` so the batch regenerates them as a
pair, rather than being left with a dark asset and no twin.

Revision ID: 0005_illustration_light_variant
Revises: 0004_session_ended_at
Create Date: 2026-08-02 00:30:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_illustration_light_variant"
down_revision: str | None = "0004_session_ended_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("exercises", sa.Column("illustration_url_light", sa.Text(), nullable=True))
    # Art generated before the style re-lock has no light twin and the wrong style; send it back
    # to 'pending' so the resumable batch picks it up. Idempotent: a re-run matches nothing.
    op.execute("""
        UPDATE exercises
           SET illustration_status = 'pending',
               illustration_url = NULL,
               illustration_url_light = NULL
         WHERE illustration_url IS NOT NULL
        """)


def downgrade() -> None:
    op.drop_column("exercises", "illustration_url_light")
