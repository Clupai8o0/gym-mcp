"""Skills-module endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, current_user, get_db
from app.schemas.skills import (
    SkillDetailOut,
    SkillOverviewItem,
    SkillProgressOut,
    SkillProgressUpsert,
    SkillsOverviewOut,
)
from app.services import skills

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("", response_model=SkillsOverviewOut)
async def skills_overview(
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillsOverviewOut:
    pairs = await skills.overview(db, user_id=cu.user_id)
    return SkillsOverviewOut(items=[SkillOverviewItem.from_pair(p) for p in pairs])


@router.get("/{slug}", response_model=SkillDetailOut)
async def skill_detail(
    slug: str,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillDetailOut:
    pair = await skills.detail(db, user_id=cu.user_id, slug=slug)
    return SkillDetailOut.from_pair(pair)


@router.put("/{slug}/progress", response_model=SkillProgressOut)
async def upsert_skill_progress(
    slug: str,
    payload: SkillProgressUpsert,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillProgressOut:
    progress = await skills.upsert_progress(
        db,
        user_id=cu.user_id,
        slug=slug,
        current_stage=payload.current_stage,
        progress_percent=payload.progress_percent,
        stage_name=payload.stage_name,
        notes=payload.notes,
    )
    return SkillProgressOut.model_validate(progress)
