"""Exercise catalog service: user-scoped listing, detail, and custom creation.

Visibility rule everywhere: a user sees **global** rows (``created_by_user_id IS NULL``)
plus their **own** custom rows. Custom slugs are unique per owner (enforced by the
partial index ``exercises_custom_slug_uidx``; we also pre-check for a clean 409).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.slugs import slugify
from app.models import Exercise

_CUSTOM_SOURCE = "custom"


def _visible_to(user_id: uuid.UUID) -> ColumnElement[bool]:
    """Global rows OR rows owned by ``user_id``."""
    return or_(Exercise.created_by_user_id.is_(None), Exercise.created_by_user_id == user_id)


def _apply_filters(
    stmt: Select[tuple[Exercise]],
    *,
    q: str | None,
    muscle: str | None,
    equipment: str | None,
    category: str | None,
    level: str | None,
) -> Select[tuple[Exercise]]:
    if q:
        stmt = stmt.where(Exercise.name.ilike(f"%{q}%"))
    if muscle:
        # ``@>`` (array contains) — uses the GIN index on primary_muscles.
        stmt = stmt.where(Exercise.primary_muscles.contains([muscle]))
    if equipment:
        stmt = stmt.where(Exercise.equipment == equipment)
    if category:
        stmt = stmt.where(Exercise.category == category)
    if level:
        stmt = stmt.where(Exercise.level == level)
    return stmt


async def list_exercises(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    q: str | None = None,
    muscle: str | None = None,
    equipment: str | None = None,
    category: str | None = None,
    level: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[Exercise], int]:
    """Return ``(rows, total)`` for the visible catalog matching the filters."""
    base = select(Exercise).where(_visible_to(user_id))
    base = _apply_filters(
        base, q=q, muscle=muscle, equipment=equipment, category=category, level=level
    )

    total = (
        await db.execute(select(func.count()).select_from(base.order_by(None).subquery()))
    ).scalar_one()

    rows = (
        (await db.execute(base.order_by(Exercise.name).limit(limit).offset(offset))).scalars().all()
    )
    return rows, total


async def get(db: AsyncSession, *, user_id: uuid.UUID, exercise_id: uuid.UUID) -> Exercise:
    """Fetch one visible exercise by id, or raise ``not_found``."""
    exercise = (
        await db.execute(select(Exercise).where(Exercise.id == exercise_id, _visible_to(user_id)))
    ).scalar_one_or_none()
    if exercise is None:
        raise errors.not_found("Exercise not found")
    return exercise


async def create_custom(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    slug: str | None = None,
    category: str | None = None,
    force: str | None = None,
    level: str | None = None,
    mechanic: str | None = None,
    equipment: str | None = None,
    primary_muscles: list[str] | None = None,
    secondary_muscles: list[str] | None = None,
    instructions: list[str] | None = None,
) -> Exercise:
    """Create a custom exercise owned by ``user_id``. Raises ``conflict`` on slug clash."""
    final_slug = slugify(slug or name)
    if not final_slug:
        raise errors.validation("Exercise name must contain at least one letter or number")

    clash = (
        await db.execute(
            select(Exercise.id).where(
                Exercise.created_by_user_id == user_id, Exercise.slug == final_slug
            )
        )
    ).first()
    if clash is not None:
        raise errors.conflict("You already have a custom exercise with this slug", slug=final_slug)

    exercise = Exercise(
        slug=final_slug,
        name=name,
        category=category,
        force=force,
        level=level,
        mechanic=mechanic,
        equipment=equipment,
        primary_muscles=primary_muscles or [],
        secondary_muscles=secondary_muscles or [],
        instructions=instructions or [],
        source=_CUSTOM_SOURCE,
        created_by_user_id=user_id,
    )
    db.add(exercise)
    try:
        await db.flush()
    except IntegrityError as exc:  # backstop for the partial-unique index / CHECKs
        raise errors.conflict("Could not create exercise (constraint violation)") from exc
    await db.refresh(exercise)
    return exercise
