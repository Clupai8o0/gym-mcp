"""Exercise catalog endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, Pagination, current_user, get_db, pagination
from app.schemas.exercises import (
    ExerciseCreate,
    ExerciseDeleteOut,
    ExerciseDetailOut,
    ExerciseListOut,
    ExerciseOut,
    ExerciseUpdate,
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


@router.get("/by-slug/{slug}", response_model=ExerciseDetailOut)
async def get_exercise_by_slug(
    slug: str,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ExerciseDetailOut:
    """Resolve a url-safe slug to its exercise (the web Library's detail-page lookup)."""
    exercise = await exercises.get_by_slug(db, user_id=cu.user_id, slug=slug)
    return ExerciseDetailOut.model_validate(exercise)


@router.get("/{exercise_id}", response_model=ExerciseDetailOut)
async def get_exercise(
    exercise_id: uuid.UUID,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ExerciseDetailOut:
    exercise = await exercises.get(db, user_id=cu.user_id, exercise_id=exercise_id)
    return ExerciseDetailOut.model_validate(exercise)


@router.patch("/{exercise_id}", response_model=ExerciseDetailOut)
async def update_exercise(
    exercise_id: uuid.UUID,
    payload: ExerciseUpdate,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ExerciseDetailOut:
    """Edit a **custom** exercise. Renaming regenerates the slug, keeping the old one as an alias."""
    exercise = await exercises.update_custom(
        db,
        user_id=cu.user_id,
        exercise_id=exercise_id,
        changes=payload.model_dump(exclude_unset=True),
    )
    return ExerciseDetailOut.model_validate(exercise)


@router.delete("/{exercise_id}", response_model=ExerciseDeleteOut)
async def delete_exercise(
    exercise_id: uuid.UUID,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    reassign_to: uuid.UUID | None = Query(default=None),
    dry_run: bool = Query(default=False),
) -> ExerciseDeleteOut:
    """Soft-delete a custom exercise, refusing to orphan the sets that reference it."""
    result = await exercises.delete_custom(
        db,
        user_id=cu.user_id,
        exercise_id=exercise_id,
        reassign_to=reassign_to,
        dry_run=dry_run,
    )
    return ExerciseDeleteOut(
        exercise=ExerciseOut.model_validate(result.exercise),
        set_count=result.set_count,
        reassigned_to=(
            ExerciseOut.model_validate(result.reassigned_to) if result.reassigned_to else None
        ),
        dry_run=result.dry_run,
        planned_count=result.planned_count,
    )


@router.post("/{exercise_id}/illustration", response_model=ExerciseDetailOut)
async def ensure_illustration(
    exercise_id: uuid.UUID,
    cu: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ExerciseDetailOut:
    """On-demand fallback (docs/06): generate + persist this exercise's illustration if missing.

    Returns the exercise; ``illustration_status`` is ``ready`` (with ``illustration_url``) on
    success, or ``generating`` if a batch run is already producing it. 503 if the image
    provider/Blob is unavailable.
    """
    # Imported here, not at module scope: `services.images` reaches the OpenAI + Blob adapters
    # and drags `httpx` (~33 ms) into every cold start to serve this one endpoint (docs/13 S1).
    from app.services import images

    exercise = await images.ensure(db, user_id=cu.user_id, exercise_id=exercise_id)
    return ExerciseDetailOut.model_validate(exercise)
