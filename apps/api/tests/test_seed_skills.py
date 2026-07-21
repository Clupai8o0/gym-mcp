"""The 13 skill definitions are seeded by migration 0002."""

from __future__ import annotations

from app.models import Skill
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

EXPECTED_SLUGS = {
    "one_arm_pull_up",
    "human_flag",
    "one_arm_push_up",
    "one_arm_handstand",
    "shrimp_squat",
    "hefesto",
    "dragon_flag",
    "muscle_up",
    "planche",
    "front_lever",
    "back_lever",
    "handstand_push_up",
    "v_sit",
}
# A few spot-checks of the stage counts ported from the legacy app.
EXPECTED_STAGES = {"planche": 6, "one_arm_handstand": 11, "v_sit": 8, "muscle_up": 5}


async def test_all_thirteen_skills_seeded(db_session: AsyncSession) -> None:
    skills = (await db_session.execute(select(Skill))).scalars().all()

    assert len(skills) == 13
    assert {skill.slug for skill in skills} == EXPECTED_SLUGS


async def test_skill_stage_counts(db_session: AsyncSession) -> None:
    by_slug = {skill.slug: skill for skill in (await db_session.execute(select(Skill))).scalars()}

    for slug, total_stages in EXPECTED_STAGES.items():
        assert by_slug[slug].total_stages == total_stages
    # Every skill has a human-readable name.
    assert all(skill.name for skill in by_slug.values())
