"""Personal records: the current best, its chronology, and manual entry.

Records reach ``personal_records`` two ways. **Auto** records are derived by PR detection in
``services/sets`` — a chronological recompute over the logged sets. **Manual** records are written
here by :func:`log_manual_pr`, for the things a set cannot express: an estimated 1RM, a hold timed
outside a session, a record carried over from another app.

The two coexist under one rule, enforced across both modules:

* A manual write **always wins** on the spot. It is an explicit correction, not a guess.
* Auto detection overwrites a manual record only when a logged set **strictly beats** it — see
  ``services/sets._sync_records``. A real 105kg squat replaces a 100kg estimate; an 80kg working
  set does not.

Every accepted write of either kind lands in ``personal_records_history``, which is what
:func:`history` reads. It used to read PR-flagged sets instead, so manual entries — having no set
— were invisible; that was the bug this module's rewrite fixes.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock, errors
from app.models import (
    PR_TYPES,
    PR_UNITS,
    Exercise,
    PersonalRecord,
    PersonalRecordHistory,
    WorkoutSession,
)
from app.services import exercises as exercises_service
from app.services import sets as sets_service


@dataclass(frozen=True)
class PrWithExercise:
    """A personal record paired with the exercise it belongs to (for display)."""

    pr: PersonalRecord
    exercise: Exercise


def require_pr_type(pr_type: str) -> str:
    """Validate a metric name, naming the alternatives when it is wrong.

    Shared by the write and read paths so ``log_pr`` and ``get_pr_history`` reject the same
    vocabulary with the same message.
    """
    if pr_type not in PR_TYPES:
        raise errors.validation(
            f"pr_type must be one of {', '.join(PR_TYPES)}", pr_type=pr_type, valid=list(PR_TYPES)
        )
    return pr_type


async def list_prs(
    db: AsyncSession, *, user_id: uuid.UUID, exercise_id: uuid.UUID | None = None
) -> Sequence[PrWithExercise]:
    """All of a user's PRs (optionally one exercise), ordered by exercise name then type."""
    stmt = (
        select(PersonalRecord, Exercise)
        .join(Exercise, PersonalRecord.exercise_id == Exercise.id)
        .where(PersonalRecord.user_id == user_id)
        .order_by(Exercise.name, PersonalRecord.pr_type)
    )
    if exercise_id is not None:
        stmt = stmt.where(PersonalRecord.exercise_id == exercise_id)
    rows = (await db.execute(stmt)).all()
    return [PrWithExercise(pr=pr, exercise=ex) for pr, ex in rows]


async def history(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    exercise_id: uuid.UUID,
    pr_type: str,
    include_deleted: bool = False,
    include_uncounted: bool = False,
) -> Sequence[PersonalRecordHistory]:
    """Every accepted PR write for one exercise + metric, oldest first.

    Manual and auto entries are interleaved chronologically; each row carries its own ``source``.
    ``created_at`` breaks ties so two entries claiming the same instant — re-stating a PR is
    allowed and keeps both — still come back in the order they were written.
    """
    require_pr_type(pr_type)
    stmt = select(PersonalRecordHistory).where(
        PersonalRecordHistory.user_id == user_id,
        PersonalRecordHistory.exercise_id == exercise_id,
        PersonalRecordHistory.pr_type == pr_type,
    )
    if not include_deleted:
        stmt = stmt.where(PersonalRecordHistory.deleted_at.is_(None))
    if not include_uncounted:
        # The chronology is what *set* records, and it promises to only rise. A hand-entered claim
        # that never beat the record standing at its moment is kept as an input (see
        # `services/integrity`) but is not part of that story.
        stmt = stmt.where(PersonalRecordHistory.counted.is_(True))
    return (
        (
            await db.execute(
                stmt.order_by(PersonalRecordHistory.achieved_at, PersonalRecordHistory.created_at)
            )
        )
        .scalars()
        .all()
    )


async def log_manual_pr(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    exercise_id: uuid.UUID,
    pr_type: str,
    value: float | Decimal,
    achieved_at: datetime,
    session_id: uuid.UUID | None = None,
    notes: str | None = None,
    client_key: str | None = None,
) -> PrWithExercise:
    """Record a PR by hand.

    A hand-entered claim is judged by the same rule as a logged set: it has to **beat the record
    standing at its own moment**. That is not a hedge against the user — it is what keeps the
    chronology monotonic. A claim below the standing best is not a new record, and storing it as
    one produced exactly the corrupted history this module now exists to repair. Backdating still
    works: a claim dated January is judged against January, not against today.

    To change a record you already have, use :func:`update_pr` — that is a correction, not a new
    achievement, and the two should not be spelled the same way.

    ``client_key`` makes the call idempotent for a retry that never saw its response.
    """
    require_pr_type(pr_type)

    if client_key is not None:
        replay = (
            await db.execute(
                select(PersonalRecordHistory).where(
                    PersonalRecordHistory.user_id == user_id,
                    PersonalRecordHistory.client_key == client_key,
                )
            )
        ).scalar_one_or_none()
        if replay is not None:
            return await _pair_for(db, user_id, replay.exercise_id, replay.pr_type)

    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    if amount <= 0:
        raise errors.validation("value must be greater than zero", value=float(amount))

    when = clock.as_utc(achieved_at)
    if when > clock.now():
        raise errors.validation("achieved_at cannot be in the future", achieved_at=when.isoformat())

    # Raises not_found for an exercise that is neither global nor this user's own.
    exercise = await exercises_service.get(db, user_id=user_id, exercise_id=exercise_id)

    if session_id is not None:
        owned = (
            await db.execute(
                select(WorkoutSession.id).where(
                    WorkoutSession.id == session_id,
                    WorkoutSession.user_id == user_id,
                    WorkoutSession.deleted_at.is_(None),
                )
            )
        ).first()
        if owned is None:
            raise errors.not_found("Session not found")

    standing = await sets_service.running_best_at(
        db, user_id=user_id, exercise_id=exercise_id, pr_type=pr_type, moment=when
    )
    if standing is not None and amount <= standing:
        raise errors.validation(
            f"{amount} {PR_UNITS[pr_type]} does not beat the {standing} "
            f"{PR_UNITS[pr_type]} standing on {when.date().isoformat()} for "
            f"{exercise.name}. Use update_pr to correct an existing record.",
            value=float(amount),
            standing=float(standing),
        )

    db.add(
        PersonalRecordHistory(
            user_id=user_id,
            exercise_id=exercise_id,
            pr_type=pr_type,
            value=amount,
            unit=PR_UNITS[pr_type],
            achieved_at=when,
            source="manual",
            set_id=None,
            session_id=session_id,
            notes=notes,
            client_key=client_key,
        )
    )
    await db.flush()

    # The replay decides what the record now is — including whether this claim or a later logged
    # set holds it. Writing `personal_records` here as well would be a second opinion.
    await sets_service.recompute(db, user_id=user_id, exercise_id=exercise_id)
    return await _pair_for(db, user_id, exercise_id, pr_type)


async def _pair_for(
    db: AsyncSession, user_id: uuid.UUID, exercise_id: uuid.UUID, pr_type: str
) -> PrWithExercise:
    """The standing record for one (exercise, metric), paired with its exercise."""
    row = (
        await db.execute(
            select(PersonalRecord, Exercise)
            .join(Exercise, PersonalRecord.exercise_id == Exercise.id)
            .where(
                PersonalRecord.user_id == user_id,
                PersonalRecord.exercise_id == exercise_id,
                PersonalRecord.pr_type == pr_type,
            )
        )
    ).first()
    if row is None:
        raise errors.not_found("Personal record not found")
    return PrWithExercise(pr=row[0], exercise=row[1])


async def get_pr(db: AsyncSession, *, user_id: uuid.UUID, pr_id: uuid.UUID) -> PersonalRecord:
    record = (
        await db.execute(
            select(PersonalRecord).where(
                PersonalRecord.id == pr_id, PersonalRecord.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise errors.not_found("Personal record not found")
    return record


async def get_history_entry(
    db: AsyncSession, *, user_id: uuid.UUID, entry_id: uuid.UUID
) -> PersonalRecordHistory:
    entry = (
        await db.execute(
            select(PersonalRecordHistory).where(
                PersonalRecordHistory.id == entry_id,
                PersonalRecordHistory.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise errors.not_found("PR history entry not found")
    return entry


async def update_pr(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    pr_id: uuid.UUID,
    value: float | Decimal | None = None,
    achieved_at: datetime | None = None,
    notes: str | None = None,
    clear_notes: bool = False,
) -> PrWithExercise:
    """Correct a hand-entered record in place, without the delete-and-reinsert dance.

    Only ``manual`` records can be edited. An ``auto`` record is a statement about a set that
    exists — the honest way to change it is to correct the set (``update_set``), which recomputes
    this row anyway. Editing it here would produce a record the log does not support, and the very
    next recalculation would silently undo it.

    The edit lands on the **history entry**, not on ``personal_records``: that entry is the input
    the replay reads, so writing it is what makes the correction stick. The record row is then
    rebuilt from it.
    """
    record = await get_pr(db, user_id=user_id, pr_id=pr_id)
    if record.source != "manual":
        raise errors.validation(
            "Only a hand-entered record can be edited directly. This one was detected from a "
            "logged set — correct the set with update_set and the record follows.",
            pr_id=str(pr_id),
            source=record.source,
        )

    entry = await _manual_entry_behind(db, user_id, record)

    if value is not None:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
        if amount <= 0:
            raise errors.validation("value must be greater than zero", value=float(amount))
        entry.value = amount
    if achieved_at is not None:
        when = clock.as_utc(achieved_at)
        if when > clock.now():
            raise errors.validation(
                "achieved_at cannot be in the future", achieved_at=when.isoformat()
            )
        entry.achieved_at = when
    if clear_notes:
        entry.notes = None
    elif notes is not None:
        entry.notes = notes

    await db.flush()
    await sets_service.recompute(db, user_id=user_id, exercise_id=record.exercise_id)

    # The correction may have moved the record onto a different entry entirely — a value edited
    # downward can hand it to a logged set. Report what is actually standing now.
    return await _pair_for(db, user_id, record.exercise_id, record.pr_type)


async def _manual_entry_behind(
    db: AsyncSession, user_id: uuid.UUID, record: PersonalRecord
) -> PersonalRecordHistory:
    """The live manual history row this record was built from.

    Matched on value + instant, which is what the replay used to promote it. A manual record
    always has one; if it somehow does not, the tables disagree and the caller should be told to
    run ``recalculate_prs`` rather than handed a confusing edit.
    """
    entry = (
        (
            await db.execute(
                select(PersonalRecordHistory)
                .where(
                    PersonalRecordHistory.user_id == user_id,
                    PersonalRecordHistory.exercise_id == record.exercise_id,
                    PersonalRecordHistory.pr_type == record.pr_type,
                    PersonalRecordHistory.source == "manual",
                    PersonalRecordHistory.deleted_at.is_(None),
                    PersonalRecordHistory.value == record.value,
                    PersonalRecordHistory.achieved_at == record.achieved_at,
                )
                .order_by(PersonalRecordHistory.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if entry is None:
        raise errors.conflict(
            "This record has no hand-entered history entry behind it; the record tables are out "
            "of step. Run recalculate_prs for this exercise first.",
            pr_id=str(record.id),
        )
    return entry


async def delete_history_entry(
    db: AsyncSession, *, user_id: uuid.UUID, entry_id: uuid.UUID, at: datetime | None = None
) -> PersonalRecordHistory:
    """Withdraw one chronology entry, then rebuild the record from what is left.

    This is the tool for a bogus row — the 60 kg entry that a since-fixed bug wrote under a squat
    whose real record was 100. Soft, so it can be restored.

    An ``auto`` entry is **derived**: deleting it is not a correction, because the next
    recalculation regenerates it from the set that earned it. Delete the set instead. Saying so is
    better than accepting the call and silently undoing it a moment later.
    """
    entry = await get_history_entry(db, user_id=user_id, entry_id=entry_id)
    if entry.source == "auto":
        raise errors.validation(
            "That entry is derived from a logged set, so removing it here would be undone by the "
            "next recalculation. Delete or edit the set instead (delete_set / update_set), or run "
            "recalculate_prs if the entry is stale.",
            entry_id=str(entry_id),
            set_id=str(entry.set_id) if entry.set_id else None,
        )

    if entry.deleted_at is None:
        entry.deleted_at = at or clock.now()
        await db.flush()
        await sets_service.recompute(db, user_id=user_id, exercise_id=entry.exercise_id)
    return entry


async def delete_pr(
    db: AsyncSession, *, user_id: uuid.UUID, pr_id: uuid.UUID, at: datetime | None = None
) -> PrWithExercise | None:
    """Remove a standing record, then fall back to the next best rather than leaving a gap.

    Expressed as withdrawing the hand-entered claim behind the record and recalculating — not as
    deleting the ``personal_records`` row. That row is derived state: deleting it directly would
    leave the input that produced it untouched, so the next recalculation would put it straight
    back. Withdrawing the claim is what actually means "I never set that".

    An ``auto`` record has no claim to withdraw — it is a statement about a set that exists — so
    this refuses and points at ``delete_set``. Returns the record now standing, or ``None`` if
    nothing supports one.
    """
    record = await get_pr(db, user_id=user_id, pr_id=pr_id)
    if record.source != "manual":
        raise errors.validation(
            "That record was detected from a logged set, so it cannot be deleted on its own — the "
            "next recalculation would restore it. Delete the set with delete_set, and the record "
            "falls back to your next best.",
            pr_id=str(pr_id),
            source=record.source,
        )

    entry = await _manual_entry_behind(db, user_id, record)
    entry.deleted_at = at or clock.now()
    await db.flush()
    await sets_service.recompute(db, user_id=user_id, exercise_id=record.exercise_id)

    try:
        return await _pair_for(db, user_id, record.exercise_id, record.pr_type)
    except errors.ServiceError:
        return None  # nothing left supports a record for this metric
