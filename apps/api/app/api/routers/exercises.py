"""Exercise catalog endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, Pagination, current_user, get_db, pagination
from app.schemas.exercises import (
    ExerciseCreate,
    ExerciseDetailOut,
    ExerciseListOut,
    ExerciseOut,
)
from app.services import exercises

router = APIRouter(prefix="/api/exercises", tags=["exercises"])


@router.get("", response_model=ExerciseListOut)
async def list_exercises(
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    page: Pagination = Depends(pagination),
    q: str | None = Query(default=None, description="Free-text match on name"),
    muscle: str | None = Query(default=None),
    equipment: str | None = Query(default=None),
    category: str | None = Query(default=None),
    level: str | None = Query(default=None),
) -> ExerciseListOut:
    rows, total = await exercises.list_exercises(
        db,
        user_id=cu.user_id,
        q=q,
        muscle=muscle,
        equipment=equipment,
        category=category,
        level=level,
        limit=page.limit,
        offset=page.offset,
    )
    return ExerciseListOut(
        items=[ExerciseOut.model_validate(row) for row in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("", response_model=ExerciseDetailOut, status_code=201)
async def create_exercise(
    payload: ExerciseCreate,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ExerciseDetailOut:
    exercise = await exercises.create_custom(db, user_id=cu.user_id, **payload.model_dump())
    return ExerciseDetailOut.model_validate(exercise)


@router.get("/{exercise_id}", response_model=ExerciseDetailOut)
async def get_exercise(
    exercise_id: uuid.UUID,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ExerciseDetailOut:
    exercise = await exercises.get(db, user_id=cu.user_id, exercise_id=exercise_id)
    return ExerciseDetailOut.model_validate(exercise)
