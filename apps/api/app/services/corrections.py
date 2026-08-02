"""Undo for soft deletes, and the one path that actually frees the storage.

Everything the correction tooling deletes is soft — the row leaves every read and
``deleted_at`` records when. That is only half a promise: without a way back it is just a
tidier permanence. :func:`restore` is the other half.

:func:`purge` is the hard delete, and it is deliberately awkward to reach: an explicit call,
an explicit age. Nothing garbage-collects on a timer, because "the row is still there" is the
property the rest of this module depends on.

Entity types are named rather than inferred from the id. A UUID says nothing about which table
it came from, so guessing would mean four lookups and an ambiguous answer when two matched.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock, errors
from app.models import Exercise, ExerciseSet, PersonalRecordHistory, WorkoutSession

#: What ``restore`` and ``purge`` can act on. The value is the mapped class; the key is what a
#: caller says.
_ENTITIES: dict[str, Any] = {
    "session": WorkoutSession,
    "set": ExerciseSet,
    "exercise": Exercise,
    "pr_history_entry": PersonalRecordHistory,
}

ENTITY_TYPES: tuple[str, ...] = tuple(_ENTITIES)


@dataclass(frozen=True)
class Restored:
    entity_type: str
    entity_id: uuid.UUID
    #: Exercises whose records were rebuilt as a consequence.
    exercises_recalculated: int


@dataclass(frozen=True)
class PurgeReport:
    older_than_days: int
    counts: dict[str, int]
    dry_run: bool

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _model_for(entity_type: str) -> Any:
    model = _ENTITIES.get(entity_type)
    if model is None:
        raise errors.validation(
            f"entity_type must be one of {', '.join(ENTITY_TYPES)}",
            entity_type=entity_type,
            valid=list(ENTITY_TYPES),
        )
    return model


async def _fetch(db: AsyncSession, model: Any, user_id: uuid.UUID, entity_id: uuid.UUID) -> Any:
    """The row, scoped to the caller. ``Exercise`` scopes by owner, everything else by ``user_id``.

    A catalog exercise has no owner and is never soft-deleted, so scoping customs by
    ``created_by_user_id`` is both correct and the only sensible reading of "your exercise".
    """
    owner = Exercise.created_by_user_id if model is Exercise else model.user_id
    row = (
        await db.execute(select(model).where(model.id == entity_id, owner == user_id))
    ).scalar_one_or_none()
    if row is None:
        raise errors.not_found("Not found")
    return row


async def restore(
    db: AsyncSession, *, user_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
) -> Restored:
    """Undo a soft delete, and rebuild whatever records depended on the row being gone.

    Restoring a **session** brings back the sets that were deleted *with* it — matched on the
    delete's timestamp, so sets deleted separately beforehand stay deleted. Anything else would
    make restore a resurrection of every set the session ever had.
    """
    model = _model_for(entity_type)
    row = await _fetch(db, model, user_id, entity_id)

    if row.deleted_at is None:
        raise errors.validation(f"That {entity_type} is not deleted", entity_id=str(entity_id))

    stamp = row.deleted_at
    row.deleted_at = None

    exercise_ids: set[uuid.UUID] = set()
    if model is WorkoutSession:
        for child in (
            (
                await db.execute(
                    select(ExerciseSet).where(
                        ExerciseSet.session_id == entity_id,
                        ExerciseSet.user_id == user_id,
                        ExerciseSet.deleted_at == stamp,
                    )
                )
            )
            .scalars()
            .all()
        ):
            child.deleted_at = None
            exercise_ids.add(child.exercise_id)
    elif model is ExerciseSet:
        exercise_ids.add(row.exercise_id)
    elif model is PersonalRecordHistory:
        exercise_ids.add(row.exercise_id)
    elif model is Exercise:
        exercise_ids.add(row.id)

    await db.flush()

    from app.services import sets as sets_service

    for exercise_id in sorted(exercise_ids):
        await sets_service.recompute(db, user_id=user_id, exercise_id=exercise_id)

    return Restored(
        entity_type=entity_type, entity_id=entity_id, exercises_recalculated=len(exercise_ids)
    )


async def purge(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    older_than_days: int,
    dry_run: bool = False,
    now: datetime | None = None,
) -> PurgeReport:
    """Hard-delete rows soft-deleted longer ago than ``older_than_days``. Irreversible.

    Ordered children-before-parents so a purge cannot trip a foreign key: sets before the
    sessions that hold them, history before the exercises it points at.

    ``older_than_days = 0`` is rejected. A purge with no window is indistinguishable from "delete
    everything I just removed", which is exactly the operation an undo is supposed to protect.
    """
    if older_than_days < 1:
        raise errors.validation(
            "older_than_days must be at least 1 — a purge with no window would take back the "
            "undo that soft delete exists to provide",
            older_than_days=older_than_days,
        )

    cutoff = (now or clock.now()) - timedelta(days=older_than_days)
    counts: dict[str, int] = {}

    # Children first: an ExerciseSet references a WorkoutSession, and history references both.
    order: Sequence[tuple[str, Any, Callable[[], Any]]] = (
        (
            "pr_history_entry",
            PersonalRecordHistory,
            lambda: (
                PersonalRecordHistory.user_id == user_id,
                PersonalRecordHistory.deleted_at.is_not(None),
                PersonalRecordHistory.deleted_at < cutoff,
            ),
        ),
        (
            "set",
            ExerciseSet,
            lambda: (
                ExerciseSet.user_id == user_id,
                ExerciseSet.deleted_at.is_not(None),
                ExerciseSet.deleted_at < cutoff,
            ),
        ),
        (
            "session",
            WorkoutSession,
            lambda: (
                WorkoutSession.user_id == user_id,
                WorkoutSession.deleted_at.is_not(None),
                WorkoutSession.deleted_at < cutoff,
            ),
        ),
        (
            "exercise",
            Exercise,
            lambda: (
                Exercise.created_by_user_id == user_id,
                Exercise.deleted_at.is_not(None),
                Exercise.deleted_at < cutoff,
            ),
        ),
    )

    for name, model, predicate in order:
        where = predicate()
        counts[name] = (
            await db.execute(select(func.count()).select_from(model).where(*where))
        ).scalar_one()
        if not dry_run and counts[name]:
            await db.execute(sa_delete(model).where(*where))

    if not dry_run:
        await db.flush()

    return PurgeReport(older_than_days=older_than_days, counts=counts, dry_run=dry_run)
