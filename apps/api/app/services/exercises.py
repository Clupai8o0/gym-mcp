"""Exercise catalog service: user-scoped listing, detail, and custom creation.

Visibility rule everywhere: a user sees **global** rows (``created_by_user_id IS NULL``)
plus their **own** custom rows. Custom slugs are unique per owner (enforced by the
partial index ``exercises_custom_slug_uidx``; we also pre-check for a clean 409).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock, errors
from app.core.slugs import slugify
from app.models import Exercise, ExerciseSet, ExerciseSlugAlias

_CUSTOM_SOURCE = "custom"


def _visible_to(user_id: uuid.UUID) -> ColumnElement[bool]:
    """Global rows OR rows owned by ``user_id`` — and live either way.

    Soft-deleted rows fold into the same predicate deliberately. Visibility is checked at every
    entry point in this module, so putting the filter here means a deleted custom exercise cannot
    reappear through a path that forgot about it.
    """
    return and_(
        Exercise.deleted_at.is_(None),
        or_(Exercise.created_by_user_id.is_(None), Exercise.created_by_user_id == user_id),
    )


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

    # ``id`` is the tiebreak, not decoration: catalog names are not unique (a user's custom row may
    # share a name with a global one), and ``ORDER BY`` on a non-unique key leaves Postgres free to
    # return tied rows in a different order per query. Under ``LIMIT/OFFSET`` paging that silently
    # duplicates and skips rows across page boundaries — which the Library's scroll pagination,
    # stitching pages into one list, would surface immediately.
    rows = (
        (await db.execute(base.order_by(Exercise.name, Exercise.id).limit(limit).offset(offset)))
        .scalars()
        .all()
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


async def get_by_slug(db: AsyncSession, *, user_id: uuid.UUID, slug: str) -> Exercise:
    """Fetch one visible exercise by exact ``slug``, or raise ``not_found``.

    The web Library addresses exercises by their url-safe slug (``/library/{slug}``), so the
    detail page resolves the slug to a row here — never in the router. A user's custom slug can
    collide with a global one (slugs are unique per owner, not globally); the **global** row
    wins, matching :func:`resolve_ref`'s global-beats-custom rule.
    """
    key = slugify(slug)
    if not key:
        raise errors.not_found("Exercise not found")
    rows = (
        (await db.execute(select(Exercise).where(Exercise.slug == key, _visible_to(user_id))))
        .scalars()
        .all()
    )
    if not rows:
        raise errors.not_found("Exercise not found")
    # Deterministic on a global/custom slug collision: global (null owner) first.
    return sorted(rows, key=lambda ex: ex.created_by_user_id is not None)[0]


async def resolve_ref(db: AsyncSession, *, user_id: uuid.UUID, ref: str) -> Exercise:
    """Resolve a UUID, slug, or name to one visible exercise (docs/04 chat-identity rule).

    Chat users say names ("bench press"), not UUIDs, so the MCP tools resolve a free-form
    reference here — never in the adapter. Resolution order: a valid **UUID** → fetch by id;
    otherwise an exact **slug** (the ref slugified) or exact case-insensitive **name** match,
    visibility-scoped (global catalog + the user's customs). On a tie, a slug hit beats a
    name-only hit and a **global** row beats a custom one; a genuine tie at that top tier
    raises ``conflict`` carrying the candidates so the caller can disambiguate by id.
    """
    ref = ref.strip()
    if not ref:
        raise errors.validation("An exercise reference cannot be empty")

    try:
        exercise_id = uuid.UUID(ref)
    except ValueError:
        pass
    else:
        return await get(db, user_id=user_id, exercise_id=exercise_id)

    key = slugify(ref)
    rows = (
        (
            await db.execute(
                select(Exercise).where(
                    _visible_to(user_id),
                    or_(Exercise.slug == key, func.lower(Exercise.name) == ref.lower()),
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        # Nothing live answers to this name — try the slugs that used to. A live slug always wins
        # (this branch is only reached when none matched), so history can never shadow the present.
        aliased = await _resolve_alias(db, user_id, key)
        if aliased is not None:
            return aliased
        raise errors.not_found(f"No exercise matches '{ref}'")

    # Rank: exact-slug before name-only, global before custom, then by name for stability.
    def _rank(ex: Exercise) -> tuple[bool, bool, str]:
        return (ex.slug != key, ex.created_by_user_id is not None, ex.name)

    ranked = sorted(rows, key=_rank)
    best = ranked[0]
    top_tier = _rank(best)[:2]
    tied = [ex for ex in ranked if _rank(ex)[:2] == top_tier]
    if len(tied) > 1:
        raise errors.conflict(
            f"Multiple exercises match '{ref}'; specify one by id",
            candidates=[{"id": str(ex.id), "name": ex.name, "slug": ex.slug} for ex in tied],
        )
    return best


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


# ── Corrections (docs/02 §Corrections) ────────────────────────────────────────────────
#: Fields a custom exercise's owner may change. `slug` is absent on purpose: it is derived from
#: the name so the two can never drift, and the old value is kept as an alias.
_CUSTOM_UPDATABLE = frozenset(
    {
        "name",
        "category",
        "force",
        "level",
        "mechanic",
        "equipment",
        "primary_muscles",
        "secondary_muscles",
        "instructions",
    }
)


async def _owned_custom(db: AsyncSession, user_id: uuid.UUID, exercise_id: uuid.UUID) -> Exercise:
    """A custom exercise this user owns. Anything else is refused with a reason, not a 404.

    A catalog row *is* visible to the caller, so a bare "not found" would be actively misleading —
    they can see it, they simply cannot change it. Shared reference data is not one user's to edit.
    """
    exercise = await get(db, user_id=user_id, exercise_id=exercise_id)
    if exercise.created_by_user_id is None:
        raise errors.validation(
            f"'{exercise.name}' is a catalog exercise shared by every user, so it cannot be "
            f"edited or deleted. Create a custom exercise instead.",
            exercise_id=str(exercise_id),
        )
    if exercise.created_by_user_id != user_id:
        raise errors.not_found("Exercise not found")
    return exercise


async def update_custom(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    exercise_id: uuid.UUID,
    changes: Mapping[str, Any],
) -> Exercise:
    """Edit a custom exercise. Renaming regenerates the slug and keeps the old one as an alias.

    The alias is the point: a slug is a public identifier that an MCP client may have stored, and
    fixing a typo in a name should not 404 every reference to it. The exercise's own ``slug`` is
    always the current one, so nothing about display or new links changes.
    """
    exercise = await _owned_custom(db, user_id, exercise_id)

    for key, value in changes.items():
        if key not in _CUSTOM_UPDATABLE:
            raise errors.validation(f"Field '{key}' is not updatable")
        setattr(exercise, key, value)

    if "name" in changes:
        new_slug = slugify(exercise.name)
        if not new_slug:
            raise errors.validation("Exercise name must contain at least one letter or number")
        if new_slug != exercise.slug:
            clash = (
                await db.execute(
                    select(Exercise.id).where(
                        Exercise.created_by_user_id == user_id,
                        Exercise.slug == new_slug,
                        Exercise.id != exercise_id,
                        Exercise.deleted_at.is_(None),
                    )
                )
            ).first()
            if clash is not None:
                raise errors.conflict(
                    "You already have a custom exercise with this slug", slug=new_slug
                )
            await _remember_slug(db, exercise, exercise.slug)
            exercise.slug = new_slug

    try:
        await db.flush()
    except IntegrityError as exc:  # backstop for the partial-unique index / CHECKs
        raise errors.conflict("Could not update exercise (constraint violation)") from exc
    await db.refresh(exercise)
    return exercise


async def _remember_slug(db: AsyncSession, exercise: Exercise, slug: str) -> None:
    """Keep ``slug`` resolvable after a rename, unless something already owns it."""
    taken = (
        await db.execute(
            select(ExerciseSlugAlias.id).where(
                ExerciseSlugAlias.created_by_user_id == exercise.created_by_user_id,
                ExerciseSlugAlias.slug == slug,
            )
        )
    ).first()
    if taken is not None:
        return  # a previous rename already claimed it; the older reference wins
    db.add(
        ExerciseSlugAlias(
            exercise_id=exercise.id,
            created_by_user_id=exercise.created_by_user_id,
            slug=slug,
        )
    )


async def _resolve_alias(db: AsyncSession, user_id: uuid.UUID, key: str) -> Exercise | None:
    """An exercise reachable only by a slug it used to have."""
    return (
        (
            await db.execute(
                select(Exercise)
                .join(ExerciseSlugAlias, ExerciseSlugAlias.exercise_id == Exercise.id)
                .where(ExerciseSlugAlias.slug == key, _visible_to(user_id))
                .order_by(Exercise.created_by_user_id.is_(None).desc())
            )
        )
        .scalars()
        .first()
    )


@dataclass(frozen=True)
class ExerciseDeletion:
    """What a custom-exercise delete did (or, under ``dry_run``, would do)."""

    exercise: Exercise
    set_count: int
    reassigned_to: Exercise | None
    dry_run: bool


async def delete_custom(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    exercise_id: uuid.UUID,
    reassign_to: uuid.UUID | None = None,
    dry_run: bool = False,
    at: datetime | None = None,
) -> ExerciseDeletion:
    """Soft-delete a custom exercise, refusing to orphan the sets that reference it.

    A set whose exercise has vanished is worse than no deletion at all: it still carries weight
    and reps into volume totals but can no longer say what movement it was. So either there are no
    sets, or ``reassign_to`` names the exercise they should belong to — in which case they are
    moved first and the records for **both** movements are recomputed, because the sets have left
    one chronology and joined another.
    """
    exercise = await _owned_custom(db, user_id, exercise_id)

    live_sets = (
        await db.execute(
            select(func.count()).where(
                ExerciseSet.exercise_id == exercise_id,
                ExerciseSet.user_id == user_id,
                ExerciseSet.deleted_at.is_(None),
            )
        )
    ).scalar_one()

    target: Exercise | None = None
    if reassign_to is not None:
        if reassign_to == exercise_id:
            raise errors.validation("reassign_to must be a different exercise")
        target = await get(db, user_id=user_id, exercise_id=reassign_to)

    if live_sets and target is None:
        raise errors.validation(
            f"'{exercise.name}' still has {live_sets} logged "
            f"set{'s' if live_sets != 1 else ''}. Pass reassign_to to move them to another "
            f"exercise first — deleting it would leave them with no movement.",
            exercise_id=str(exercise_id),
            set_count=live_sets,
        )

    if dry_run:
        return ExerciseDeletion(
            exercise=exercise, set_count=live_sets, reassigned_to=target, dry_run=True
        )

    if target is not None and live_sets:
        for row in (
            (
                await db.execute(
                    select(ExerciseSet).where(
                        ExerciseSet.exercise_id == exercise_id,
                        ExerciseSet.user_id == user_id,
                        ExerciseSet.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        ):
            row.exercise_id = target.id

    exercise.deleted_at = at or clock.now()
    await db.flush()

    from app.services import sets as sets_service

    await sets_service.recompute(db, user_id=user_id, exercise_id=exercise_id)
    if target is not None:
        await sets_service.recompute(db, user_id=user_id, exercise_id=target.id)

    return ExerciseDeletion(
        exercise=exercise, set_count=live_sets, reassigned_to=target, dry_run=False
    )
