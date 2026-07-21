"""seed the 13 skill definitions (docs/02-data-model.md — Skills module).

Reference data ported from the legacy app's hardcoded calisthenics skills, now
table-driven. Stage counts come from ``lib/tools/skills.ts`` in the archived repo.
Seeding lives in its own migration so ``alembic upgrade head`` yields a fully-seeded
DB on any fresh branch; it is inherently idempotent (a migration applies once) and
reversed by ``downgrade`` deleting exactly these slugs.

Revision ID: 0002_seed_skills
Revises: 0001_init
Create Date: 2026-07-21 15:24:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_seed_skills"
down_revision: str | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (slug, display name, total_stages) — the 13 tracked skills.
SKILLS: list[tuple[str, str, int]] = [
    ("one_arm_pull_up", "One-Arm Pull-Up", 6),
    ("human_flag", "Human Flag", 8),
    ("one_arm_push_up", "One-Arm Push-Up", 8),
    ("one_arm_handstand", "One-Arm Handstand", 11),
    ("shrimp_squat", "Shrimp Squat", 5),
    ("hefesto", "Hefesto", 6),
    ("dragon_flag", "Dragon Flag", 7),
    ("muscle_up", "Muscle-Up", 5),
    ("planche", "Planche", 6),
    ("front_lever", "Front Lever", 6),
    ("back_lever", "Back Lever", 5),
    ("handstand_push_up", "Handstand Push-Up", 5),
    ("v_sit", "V-Sit", 8),
]


def upgrade() -> None:
    skills = sa.table(
        "skills",
        sa.column("slug", sa.Text),
        sa.column("name", sa.Text),
        sa.column("total_stages", sa.Integer),
    )
    op.bulk_insert(
        skills,
        [
            {"slug": slug, "name": name, "total_stages": total_stages}
            for slug, name, total_stages in SKILLS
        ],
    )


def downgrade() -> None:
    slugs = ", ".join(f"'{slug}'" for slug, _name, _stages in SKILLS)
    op.execute(f"DELETE FROM skills WHERE slug IN ({slugs})")
