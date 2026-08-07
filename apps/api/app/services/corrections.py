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
from app.models import Exercise, ExerciseSet, PersonalRecordHistory, PlannedSet, WorkoutSession

#: What ``restore`` and ``purge`` can act on. The value is the mapped class; the key is what a
#: caller says.
_ENTITIES: dict[str, Any] = {
    "session": WorkoutSession,
    "set": ExerciseSet,
    "exercise": Exercise,
    "pr_history_entry": PersonalRecordHistory,
    "planned_set": PlannedSet,
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

    Restoring a **session** brings back the sets *and the prescribed lines* that were deleted with
    it — matched on the delete's timestamp, so anything deleted separately beforehand stays
    deleted. Anything else would make restore a resurrection of every set the session ever had.

    A **planned_set** restores on its own and rebuilds nothing: a prescription is not an input to
    any record, so there is nothing derived from it to recompute. It comes back still pointing at
    the set that completed it — unless another line has claimed that set in the meantime, in which
    case it comes back outstanding, because the training is somewhere else now (see
    :func:`app.services.plans.reopen_if_claim_taken`). Restoring it with the claim intact would put
    two live rows in the partial unique index and turn the **undo** into a 500.
    """
    model = _model_for(entity_type)
    row = await _fetch(db, model, user_id, entity_id)

    if row.deleted_at is None:
        raise errors.validation(f"That {entity_type} is not deleted", entity_id=str(entity_id))

    stamp = row.deleted_at
    if model is PlannedSet:
        from app.services import plans

        await plans.reopen_if_claim_taken(db, row)
    row.deleted_at = None

    exercise_ids: set[uuid.UUID] = set()
    if model is WorkoutSession:
        from app.services import plans

        await plans.restore_for_session(db, session_id=entity_id, at=stamp)
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
    sessions that hold them, history before the exercises it points at, prescribed lines before
    the sets they name (``planned_sets.completed_set_id`` is ``ON DELETE SET NULL``, so the order
    is belt-and-braces rather than load-bearing — but a purge that depends on a cascade to stay
    upright is one schema change from breaking).

    Ordering alone is not enough for **exercises**, because each table is filtered by its *own*
    age: an exercise deleted 90 days ago and a set deleted 5 days ago sit on opposite sides of any
    cutoff, and neither ``exercise_sets.exercise_id`` nor ``planned_sets.exercise_id`` carries an
    ``ON DELETE`` clause. An exercise still referenced by anything is therefore skipped rather than
    attempted; it goes on a later run, once the rows naming it have aged out too.

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
            "planned_set",
            PlannedSet,
            lambda: (
                PlannedSet.user_id == user_id,
                PlannedSet.deleted_at.is_not(None),
                PlannedSet.deleted_at < cutoff,
            ),
        ),
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
                # …and nothing still points at it. `exercise_sets.exercise_id` and
                # `planned_sets.exercise_id` are plain foreign keys with no `ON DELETE`, and the
                # rows referencing a deleted exercise are filtered by *their own* age — so an
                # exercise removed 90 days ago and a set removed 5 days ago fall on opposite sides
                # of any cutoff, and the DELETE below raises a foreign-key violation that reaches
                # the caller as a 500 rather than a purge. Declining to purge is the right answer:
                # the exercise is still referenced, and it will go on the next run once the rows
                # naming it have aged out too.
                ~select(ExerciseSet.id).where(ExerciseSet.exercise_id == Exercise.id).exists(),
                ~select(PlannedSet.id).where(PlannedSet.exercise_id == Exercise.id).exists(),
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
