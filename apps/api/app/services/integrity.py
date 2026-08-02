"""PR recalculation and integrity verification — the repair path for the record tables.

``personal_records`` and ``personal_records_history`` are **derived state**. Their ground truth is:

* every live, non-backfill set the user has logged, ordered by its session's ``performed_at``; and
* every live ``manual`` entry in ``personal_records_history`` — a claim about a moment that has no
  set behind it (an estimated 1RM, a hold timed outside a session, a PR carried from another app).

:func:`recalculate` rebuilds both tables from those inputs. Every correction — editing a set,
deleting a session, withdrawing a hand-entered record — routes through it, which is what keeps the
two tables from disagreeing with the log or with each other. Exposing it directly is also the only
way to repair data that is *already* wrong: a chronology corrupted by a bug that has since been
fixed will not fix itself, because nothing recomputes an exercise nobody touches.

**The invariant it exists to hold:** for every (exercise, metric), the counted chronology is
strictly increasing and its last value is the standing record. :func:`verify` checks exactly that
and is cheap enough to run as a post-migration assertion or a CI test.

The subtle part is ``counted``. ``auto`` rows are output — they are written only when a set sets a
record, so they always count. ``manual`` rows are *input*: the claim has to stay in the table so a
later replay can use it, but a claim that never beat the running best at its own moment must not
appear in the chronology, or history stops being monotonic. Marking it rather than rejecting it is
what lets it count again later when the set that outranked it is deleted.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.models import (
    PR_TYPES,
    PR_UNITS,
    Exercise,
    ExerciseSet,
    PersonalRecord,
    PersonalRecordHistory,
    WorkoutSession,
)
from app.services import sets as sets_service


@dataclass(frozen=True)
class MetricResult:
    """What the rebuild produced for one (exercise, metric)."""

    exercise_id: uuid.UUID
    exercise_name: str
    pr_type: str
    #: The standing record after the rebuild, or ``None`` if nothing supports one any more.
    value: Decimal | None
    source: str | None
    #: How many chronology entries survived.
    entries: int
    #: True when the rebuild changed the stored record's value or source.
    changed: bool


@dataclass(frozen=True)
class RecalculationReport:
    exercises: int
    metrics: Sequence[MetricResult]

    @property
    def changed(self) -> Sequence[MetricResult]:
        return [m for m in self.metrics if m.changed]


@dataclass(frozen=True)
class IntegrityProblem:
    exercise_id: uuid.UUID
    exercise_name: str
    pr_type: str
    #: ``non_monotonic_history`` | ``record_disagrees_with_history`` | ``record_without_history``
    #: | ``history_without_record``
    kind: str
    detail: str


@dataclass(frozen=True)
class IntegrityReport:
    checked_exercises: int
    problems: Sequence[IntegrityProblem]

    @property
    def ok(self) -> bool:
        return not self.problems


async def _exercises_with_data(
    db: AsyncSession, user_id: uuid.UUID, exercise_id: uuid.UUID | None
) -> list[uuid.UUID]:
    """Every exercise this user has any record-relevant data for.

    Deliberately the **union** of sets and history rather than just sets: an exercise whose only
    data is a stale record row still needs visiting, or the repair path can never clear it.
    Soft-deleted rows are included here on purpose — an exercise whose last set was just deleted is
    precisely the one whose records need rebuilding.
    """
    if exercise_id is not None:
        return [exercise_id]

    from_sets = select(distinct(ExerciseSet.exercise_id)).where(ExerciseSet.user_id == user_id)
    from_history = select(distinct(PersonalRecordHistory.exercise_id)).where(
        PersonalRecordHistory.user_id == user_id
    )
    from_records = select(distinct(PersonalRecord.exercise_id)).where(
        PersonalRecord.user_id == user_id
    )
    found: set[uuid.UUID] = set()
    for stmt in (from_sets, from_history, from_records):
        found.update((await db.execute(stmt)).scalars().all())
    return sorted(found)


async def _exercise_names(
    db: AsyncSession, exercise_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not exercise_ids:
        return {}
    rows = (
        await db.execute(select(Exercise.id, Exercise.name).where(Exercise.id.in_(exercise_ids)))
    ).all()
    return {row_id: name for row_id, name in rows}


async def _chronology(
    db: AsyncSession, user_id: uuid.UUID, exercise_id: uuid.UUID, pr_type: str
) -> list[PersonalRecordHistory]:
    """The counted, live chronology for one metric, oldest first."""
    return list(
        (
            await db.execute(
                select(PersonalRecordHistory)
                .where(
                    PersonalRecordHistory.user_id == user_id,
                    PersonalRecordHistory.exercise_id == exercise_id,
                    PersonalRecordHistory.pr_type == pr_type,
                    PersonalRecordHistory.deleted_at.is_(None),
                    PersonalRecordHistory.counted.is_(True),
                )
                .order_by(PersonalRecordHistory.achieved_at, PersonalRecordHistory.created_at)
            )
        )
        .scalars()
        .all()
    )


async def recalculate(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    exercise_id: uuid.UUID | None = None,
    pr_type: str | None = None,
    dry_run: bool = False,
) -> RecalculationReport:
    """Rebuild ``personal_records`` + ``personal_records_history`` from ground truth.

    ``exercise_id`` narrows the rebuild to one movement; ``pr_type`` narrows the *report* to one
    metric. The rebuild itself is always whole-exercise — the metrics share a chronology, so
    rebuilding one in isolation could leave the others describing a different set of sets.

    ``dry_run`` runs the whole rebuild inside a **savepoint** and rolls that back, so the report
    says what would change and the tables do not move. A savepoint rather than
    ``session.rollback()``: the session belongs to the caller, and rolling it back would discard
    whatever else the request had already done — which is a much larger promise than "changed
    nothing".
    """
    if pr_type is not None:
        sets_service.require_pr_type_for_report(pr_type)

    targets = await _exercises_with_data(db, user_id, exercise_id)
    names = await _exercise_names(db, targets)

    savepoint = await db.begin_nested() if dry_run else None

    before: dict[tuple[uuid.UUID, str], tuple[Decimal, str]] = {}
    for target in targets:
        for record in (
            (
                await db.execute(
                    select(PersonalRecord).where(
                        PersonalRecord.user_id == user_id,
                        PersonalRecord.exercise_id == target,
                    )
                )
            )
            .scalars()
            .all()
        ):
            before[(target, record.pr_type)] = (record.value, record.source)

    for target in targets:
        await sets_service.recompute(db, user_id=user_id, exercise_id=target)

    metrics: list[MetricResult] = []
    for target in targets:
        after = {
            record.pr_type: record
            for record in (
                (
                    await db.execute(
                        select(PersonalRecord).where(
                            PersonalRecord.user_id == user_id,
                            PersonalRecord.exercise_id == target,
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
        for metric in PR_TYPES:
            if pr_type is not None and metric != pr_type:
                continue
            rebuilt = after.get(metric)
            was = before.get((target, metric))
            now = (rebuilt.value, rebuilt.source) if rebuilt is not None else None
            entries = len(await _chronology(db, user_id, target, metric))
            if was is None and now is None and entries == 0:
                continue  # nothing here before, nothing here now — not worth reporting
            metrics.append(
                MetricResult(
                    exercise_id=target,
                    exercise_name=names.get(target, "?"),
                    pr_type=metric,
                    value=rebuilt.value if rebuilt else None,
                    source=rebuilt.source if rebuilt else None,
                    entries=entries,
                    changed=was != now,
                )
            )

    if savepoint is not None:
        # The report is already materialized as plain values, so unwinding the savepoint discards
        # every write the rebuild made — and nothing the caller made before it.
        await savepoint.rollback()

    return RecalculationReport(exercises=len(targets), metrics=metrics)


async def verify(
    db: AsyncSession, *, user_id: uuid.UUID, exercise_id: uuid.UUID | None = None
) -> IntegrityReport:
    """Read-only: report every (exercise, metric) whose record tables disagree with themselves.

    Four ways they can:

    * **non_monotonic_history** — a counted entry that does not strictly beat the one before it.
      This is the corruption a since-fixed bug leaves behind (`100, 60, 100, 110`).
    * **record_disagrees_with_history** — the standing record is not the last counted entry.
    * **record_without_history** — a record with no chronology to justify it.
    * **history_without_record** — a chronology with no standing record at its end.

    Never writes, so it is safe to run against production and cheap enough for CI.
    """
    targets = await _exercises_with_data(db, user_id, exercise_id)
    names = await _exercise_names(db, targets)
    problems: list[IntegrityProblem] = []

    for target in targets:
        records = {
            record.pr_type: record
            for record in (
                (
                    await db.execute(
                        select(PersonalRecord).where(
                            PersonalRecord.user_id == user_id,
                            PersonalRecord.exercise_id == target,
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
        for metric in PR_TYPES:
            entries = await _chronology(db, user_id, target, metric)
            record = records.get(metric)

            previous: Decimal | None = None
            for entry in entries:
                if previous is not None and entry.value <= previous:
                    problems.append(
                        IntegrityProblem(
                            exercise_id=target,
                            exercise_name=names.get(target, "?"),
                            pr_type=metric,
                            kind="non_monotonic_history",
                            detail=(
                                f"{entry.value} at {entry.achieved_at.isoformat()} does not beat "
                                f"the preceding {previous}"
                            ),
                        )
                    )
                previous = entry.value

            if record is None and entries:
                problems.append(
                    IntegrityProblem(
                        exercise_id=target,
                        exercise_name=names.get(target, "?"),
                        pr_type=metric,
                        kind="history_without_record",
                        detail=f"{len(entries)} counted entries but no standing record",
                    )
                )
            elif record is not None and not entries:
                problems.append(
                    IntegrityProblem(
                        exercise_id=target,
                        exercise_name=names.get(target, "?"),
                        pr_type=metric,
                        kind="record_without_history",
                        detail=f"record {record.value} has no chronology behind it",
                    )
                )
            elif record is not None and entries and record.value != entries[-1].value:
                problems.append(
                    IntegrityProblem(
                        exercise_id=target,
                        exercise_name=names.get(target, "?"),
                        pr_type=metric,
                        kind="record_disagrees_with_history",
                        detail=(
                            f"record is {record.value} but the last counted entry is "
                            f"{entries[-1].value}"
                        ),
                    )
                )

    return IntegrityReport(checked_exercises=len(targets), problems=problems)


async def exercises_touched_by_session(
    db: AsyncSession, *, user_id: uuid.UUID, session_id: uuid.UUID
) -> list[uuid.UUID]:
    """Every exercise with a set in this session — the recalculation scope for a session change.

    Includes soft-deleted sets: a session being deleted is exactly the case where the sets that
    matter are the ones about to stop counting.
    """
    return list(
        (
            await db.execute(
                select(distinct(ExerciseSet.exercise_id)).where(
                    ExerciseSet.user_id == user_id, ExerciseSet.session_id == session_id
                )
            )
        )
        .scalars()
        .all()
    )


async def cascade_achieved_at(
    db: AsyncSession, *, user_id: uuid.UUID, session_id: uuid.UUID
) -> None:
    """Move any manual PR pinned to this session to the session's (possibly corrected) date.

    Auto entries need nothing — they are re-derived from ``session.performed_at`` on the next
    recalculation. A manual entry stores its own ``achieved_at``, so correcting the date of the
    session it was attached to would otherwise leave the record claiming a day the workout no
    longer happened on.
    """
    session = (
        await db.execute(
            select(WorkoutSession).where(
                WorkoutSession.id == session_id, WorkoutSession.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if session is None:
        return

    for row in (
        (
            await db.execute(
                select(PersonalRecordHistory).where(
                    PersonalRecordHistory.user_id == user_id,
                    PersonalRecordHistory.session_id == session_id,
                    PersonalRecordHistory.source == "manual",
                    PersonalRecordHistory.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    ):
        row.achieved_at = session.performed_at

    for record in (
        (
            await db.execute(
                select(PersonalRecord).where(
                    PersonalRecord.user_id == user_id,
                    PersonalRecord.session_id == session_id,
                    PersonalRecord.source == "manual",
                )
            )
        )
        .scalars()
        .all()
    ):
        record.achieved_at = session.performed_at

    await db.flush()


def unit_for(pr_type: str) -> str:
    if pr_type not in PR_UNITS:
        raise errors.validation(
            f"pr_type must be one of {', '.join(PR_TYPES)}", pr_type=pr_type, valid=list(PR_TYPES)
        )
    return PR_UNITS[pr_type]
