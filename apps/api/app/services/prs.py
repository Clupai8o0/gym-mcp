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
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.models import (
    PR_TYPES,
    PR_UNITS,
    Exercise,
    PersonalRecord,
    PersonalRecordHistory,
    WorkoutSession,
)
from app.services import exercises as exercises_service


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


def _as_utc(moment: datetime) -> datetime:
    """Treat a naive instant as UTC.

    MCP clients hand us whatever their JSON carried, and a naive value compared against an aware
    ``now()`` raises ``TypeError`` rather than failing validation cleanly. The column is
    ``timestamptz``, so UTC is the only defensible reading of a bare timestamp.
    """
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


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
    db: AsyncSession, *, user_id: uuid.UUID, exercise_id: uuid.UUID, pr_type: str
) -> Sequence[PersonalRecordHistory]:
    """Every accepted PR write for one exercise + metric, oldest first.

    Manual and auto entries are interleaved chronologically; each row carries its own ``source``.
    ``created_at`` breaks ties so two entries claiming the same instant — re-stating a PR is
    allowed and keeps both — still come back in the order they were written.
    """
    require_pr_type(pr_type)
    return (
        (
            await db.execute(
                select(PersonalRecordHistory)
                .where(
                    PersonalRecordHistory.user_id == user_id,
                    PersonalRecordHistory.exercise_id == exercise_id,
                    PersonalRecordHistory.pr_type == pr_type,
                )
                .order_by(PersonalRecordHistory.achieved_at, PersonalRecordHistory.created_at)
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
) -> PrWithExercise:
    """Record a PR by hand, overwriting whatever is stored for this exercise + metric.

    Unconditional by design: the caller is stating a fact about their own training, so this is not
    the place to argue with them. Auto detection is the side that has to prove it is better.
    """
    require_pr_type(pr_type)

    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    if amount <= 0:
        raise errors.validation("value must be greater than zero", value=float(amount))

    when = _as_utc(achieved_at)
    if when > datetime.now(UTC):
        raise errors.validation("achieved_at cannot be in the future", achieved_at=when.isoformat())

    # Raises not_found for an exercise that is neither global nor this user's own.
    exercise = await exercises_service.get(db, user_id=user_id, exercise_id=exercise_id)

    if session_id is not None:
        owned = (
            await db.execute(
                select(WorkoutSession.id).where(
                    WorkoutSession.id == session_id, WorkoutSession.user_id == user_id
                )
            )
        ).first()
        if owned is None:
            raise errors.not_found("Session not found")

    unit = PR_UNITS[pr_type]
    current = (
        await db.execute(
            select(PersonalRecord).where(
                PersonalRecord.user_id == user_id,
                PersonalRecord.exercise_id == exercise_id,
                PersonalRecord.pr_type == pr_type,
            )
        )
    ).scalar_one_or_none()

    if current is None:
        current = PersonalRecord(
            user_id=user_id,
            exercise_id=exercise_id,
            pr_type=pr_type,
            value=amount,
            unit=unit,
            achieved_at=when,
            session_id=session_id,
            notes=notes,
            source="manual",
        )
        db.add(current)
    else:
        current.value = amount
        current.unit = unit
        current.achieved_at = when
        current.session_id = session_id
        current.notes = notes
        current.source = "manual"

    # Append-only: nothing in the auto rebuild touches manual rows, so re-stating a PR leaves both
    # entries in the chronology rather than replacing the earlier claim.
    db.add(
        PersonalRecordHistory(
            user_id=user_id,
            exercise_id=exercise_id,
            pr_type=pr_type,
            value=amount,
            unit=unit,
            achieved_at=when,
            source="manual",
            set_id=None,
            session_id=session_id,
            notes=notes,
        )
    )

    await db.flush()
    return PrWithExercise(pr=current, exercise=exercise)
