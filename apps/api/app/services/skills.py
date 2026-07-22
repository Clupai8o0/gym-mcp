"""Skills module: read the 13-skill catalog with the user's progress; upsert progress.

Skills the user has never touched appear as stage 0 / 0% (no ``skill_progress`` row),
so the overview always returns the full catalog.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.models import Skill, SkillProgress


@dataclass(frozen=True)
class SkillWithProgress:
    """A skill definition plus this user's progress (``None`` if not started)."""

    skill: Skill
    progress: SkillProgress | None


async def overview(db: AsyncSession, *, user_id: uuid.UUID) -> Sequence[SkillWithProgress]:
    """Every skill with the user's progress (or ``None``), ordered by name."""
    progress_rows = (
        (await db.execute(select(SkillProgress).where(SkillProgress.user_id == user_id)))
        .scalars()
        .all()
    )
    by_skill = {p.skill_id: p for p in progress_rows}
    skills = (await db.execute(select(Skill).order_by(Skill.name))).scalars().all()
    return [SkillWithProgress(skill=s, progress=by_skill.get(s.id)) for s in skills]


async def _skill_by_slug(db: AsyncSession, slug: str) -> Skill:
    skill = (await db.execute(select(Skill).where(Skill.slug == slug))).scalar_one_or_none()
    if skill is None:
        raise errors.not_found("Skill not found", slug=slug)
    return skill


async def detail(db: AsyncSession, *, user_id: uuid.UUID, slug: str) -> SkillWithProgress:
    skill = await _skill_by_slug(db, slug)
    progress = (
        await db.execute(
            select(SkillProgress).where(
                SkillProgress.user_id == user_id, SkillProgress.skill_id == skill.id
            )
        )
    ).scalar_one_or_none()
    return SkillWithProgress(skill=skill, progress=progress)


async def upsert_progress(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    slug: str,
    current_stage: int,
    progress_percent: int,
    stage_name: str | None = None,
    notes: str | None = None,
) -> SkillProgress:
    """Create or update the user's progress for a skill (validated against its stages)."""
    skill = await _skill_by_slug(db, slug)

    if not 0 <= progress_percent <= 100:
        raise errors.validation("progress_percent must be between 0 and 100")
    if current_stage < 0 or current_stage > skill.total_stages:
        raise errors.validation(
            f"current_stage must be between 0 and {skill.total_stages}",
            total_stages=skill.total_stages,
        )

    progress = (
        await db.execute(
            select(SkillProgress).where(
                SkillProgress.user_id == user_id, SkillProgress.skill_id == skill.id
            )
        )
    ).scalar_one_or_none()

    if progress is None:
        progress = SkillProgress(user_id=user_id, skill_id=skill.id)
        db.add(progress)
    progress.current_stage = current_stage
    progress.stage_name = stage_name
    progress.progress_percent = progress_percent
    progress.notes = notes

    await db.flush()
    await db.refresh(progress)
    return progress
