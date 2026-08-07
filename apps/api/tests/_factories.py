"""Async row factories for service-layer tests (write straight to the test session)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models import Exercise, PlannedSet, User, WorkoutSession
from sqlalchemy.ext.asyncio import AsyncSession


async def make_user(db: AsyncSession, *, email: str = "lifter@example.com") -> User:
    user = User(email=email, google_sub=f"sub-{email}", name="Test Lifter")
    db.add(user)
    await db.flush()
    return user


async def make_global_exercise(
    db: AsyncSession, *, slug: str = "bench-press", name: str = "Bench Press"
) -> Exercise:
    exercise = Exercise(slug=slug, name=name)
    db.add(exercise)
    await db.flush()
    return exercise


async def make_custom_exercise(
    db: AsyncSession, *, user_id: uuid.UUID, slug: str, name: str
) -> Exercise:
    exercise = Exercise(slug=slug, name=name, source="custom", created_by_user_id=user_id)
    db.add(exercise)
    await db.flush()
    return exercise


async def make_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    performed_at: datetime | None = None,
    title: str | None = None,
    type: str | None = None,
) -> WorkoutSession:
    session = WorkoutSession(
        user_id=user_id,
        performed_at=performed_at or datetime.now(tz=UTC),
        title=title,
        type=type,
    )
    db.add(session)
    await db.flush()
    return session


async def make_planned_set(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    exercise_id: uuid.UUID,
    set_number: int = 1,
    order_index: int = 0,
    target_reps_min: int | None = None,
    target_reps_max: int | None = None,
    target_weight_kg: float | None = None,
) -> PlannedSet:
    """A prescribed line written straight to the row, bypassing the service.

    For tests that need a plan to *exist* rather than to exercise how one is written.
    """
    planned = PlannedSet(
        user_id=user_id,
        session_id=session_id,
        exercise_id=exercise_id,
        set_number=set_number,
        order_index=order_index,
        target_reps_min=target_reps_min,
        target_reps_max=target_reps_max,
        target_weight_kg=target_weight_kg,
    )
    db.add(planned)
    await db.flush()
    return planned
