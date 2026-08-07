"""Planned (prescribed) sets — what a session is *meant* to contain, next to what it did.

Until now a session could only hold sets that had already happened, so a coach-written plan had
nowhere to live: the only way to express "5×5 at 100 kg on Tuesday" was to log five sets that
nobody had done, which is a lie the moment anything reads volume or records.

The prescription therefore lives in its **own table** (:class:`app.models.PlannedSet`), and this
module is the only thing that writes it. Two rules hold the whole design up:

**A plan is never data about training.** Volume, tonnage, frequency and PR detection read
``exercise_sets`` and nothing else, so a prescription cannot inflate a number however it is
written. There is no flag for six aggregate queries to remember to exclude, because there is
nothing in those tables to exclude. :func:`complete` is the single door between the two worlds: it
writes a real logged set through ``services/sets.log_set`` — normal PR detection, normal
idempotency, normal everything — and then records that set's id on the planned row.

**Completion is read through the link, never from it.** ``completed_set_id`` pointing somewhere is
not enough; the set it names has to still be live. That is what makes deleting a logged set put its
prescribed row back to pending with no second write, and what stops a soft-deleted set from being
counted as adherence. Every count in this module goes through the same join, so "how far in am I?"
cannot disagree with "what is still to do?".

**Logging off-plan is always allowed.** Nothing here gates ``log_set``. A session with a plan can
hold sets nobody prescribed — you added a movement, you did an extra set, you swapped an exercise —
and :func:`progress` reports those as ``off_plan`` rather than refusing them. A tool that blocks
training because it wasn't written down first is worse than no plan at all.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock, errors
from app.models import Exercise, ExerciseSet, PlannedSet, WorkoutSession
from app.services import sessions as sessions_service
from app.services import sets as sets_service

# Fields a PATCH may change on a planned row (values are already Pydantic-validated by the
# router). `exercise_id` and `session_id` are absent deliberately: moving a prescription to a
# different movement or a different day is not an edit of that line, it is a different line —
# delete it and add the one you meant, so the plan's history says what actually happened to it.
_UPDATABLE = frozenset(
    {
        "set_number",
        "order_index",
        "target_reps_min",
        "target_reps_max",
        "target_weight_kg",
        "target_rpe",
        "target_hold_seconds",
        "notes",
    }
)


@dataclass(frozen=True)
class PlannedSetDraft:
    """One line of a prescription, before it has been given a session.

    ``order_index`` is optional because a caller writing a plan top to bottom should not have to
    number it: left as ``None`` the rows are numbered in the order they arrive, continuing from
    whatever the session already holds.
    """

    exercise_id: uuid.UUID
    set_number: int = 1
    order_index: int | None = None
    target_reps_min: int | None = None
    target_reps_max: int | None = None
    target_weight_kg: float | None = None
    target_rpe: float | None = None
    target_hold_seconds: int | None = None
    notes: str | None = None
    client_key: str | None = None


@dataclass(frozen=True)
class PlannedItem:
    """One prescribed set and the logged set that satisfied it, if one has.

    ``completed_set`` is the **live** set or nothing at all — a soft-deleted set is not a
    completion, which is what makes deleting it reopen the line.
    """

    planned: PlannedSet
    completed_set: ExerciseSet | None

    @property
    def is_completed(self) -> bool:
        return self.completed_set is not None


@dataclass(frozen=True)
class PlannedSession:
    """A session's whole prescription, in reading order, with each line's completion state."""

    session: WorkoutSession
    items: Sequence[PlannedItem]
    exercises: dict[uuid.UUID, Exercise]

    @property
    def planned_total(self) -> int:
        return len(self.items)

    @property
    def completed_count(self) -> int:
        return sum(1 for item in self.items if item.is_completed)


@dataclass(frozen=True)
class Adherence:
    """How much of the prescription was actually done.

    ``percent`` is ``None`` — not ``0`` and not ``100`` — when nothing was prescribed. A session
    logged without a plan has no adherence to report, and either number would be a claim about a
    plan that never existed.
    """

    planned_total: int
    completed_count: int
    pending_count: int
    #: Live sets in the session that no prescribed line claims. Training off-plan is allowed; this
    #: is how much of it there was, not a complaint about it.
    off_plan_count: int
    percent: float | None


@dataclass(frozen=True)
class ExerciseProgress:
    """One movement's share of the prescription."""

    exercise: Exercise
    planned: int
    completed: int

    @property
    def remaining(self) -> int:
        return self.planned - self.completed


@dataclass(frozen=True)
class SessionProgress:
    """Planned vs done for one session, plus what to do next."""

    session: WorkoutSession
    adherence: Adherence
    #: Every live set logged into the session, on-plan or not.
    logged_total: int
    exercises: Sequence[ExerciseProgress]
    #: The first prescribed line still outstanding, in the plan's own order.
    next_up: PlannedItem | None

    @property
    def remaining_exercises(self) -> Sequence[ExerciseProgress]:
        return [item for item in self.exercises if item.remaining > 0]


@dataclass(frozen=True)
class CompletedPlannedSet:
    """The prescribed line and the set that just satisfied it (with its PR verdict)."""

    item: PlannedItem
    logged: sets_service.LoggedSet


# ── Internals ────────────────────────────────────────────────────────────────────────
async def _owned_session(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
) -> WorkoutSession:
    """The user's session, or ``not_found`` — someone else's reads the same as missing."""
    session = (
        await db.execute(
            select(WorkoutSession).where(
                WorkoutSession.id == session_id,
                WorkoutSession.user_id == user_id,
                WorkoutSession.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if session is None:
        raise errors.not_found("Session not found")
    return session


async def _owned_planned(
    db: AsyncSession, user_id: uuid.UUID, planned_set_id: uuid.UUID
) -> PlannedSet:
    planned = (
        await db.execute(
            select(PlannedSet).where(
                PlannedSet.id == planned_set_id,
                PlannedSet.user_id == user_id,
                PlannedSet.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if planned is None:
        raise errors.not_found("Planned set not found")
    return planned


def _to_decimal(value: float | int | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _validate_targets(
    *,
    reps_min: int | None,
    reps_max: int | None,
    weight_kg: Decimal | None,
    rpe: Decimal | None,
    hold_seconds: int | None,
    where: str = "",
) -> None:
    """Reject a prescription that cannot be met.

    A planned row with **no** target is deliberately legal: "bench press, three sets, work up to
    something heavy" is a real instruction, and forcing a number out of it would mean inventing
    one. What is not legal is a target that contradicts itself — a rep range that counts down, a
    negative load — because nothing downstream can interpret it.
    """
    prefix = f"{where}: " if where else ""
    if reps_min is not None and reps_min < 0:
        raise errors.validation(f"{prefix}target_reps_min cannot be negative")
    if reps_max is not None and reps_max < 0:
        raise errors.validation(f"{prefix}target_reps_max cannot be negative")
    if reps_min is not None and reps_max is not None and reps_max < reps_min:
        raise errors.validation(
            f"{prefix}target_reps_max must be at least target_reps_min",
            target_reps_min=reps_min,
            target_reps_max=reps_max,
        )
    if weight_kg is not None and weight_kg < 0:
        raise errors.validation(f"{prefix}target_weight_kg cannot be negative")
    if hold_seconds is not None and hold_seconds < 0:
        raise errors.validation(f"{prefix}target_hold_seconds cannot be negative")
    if rpe is not None and not (1 <= rpe <= 10):
        raise errors.validation(
            f"{prefix}target_rpe must be between 1 and 10", target_rpe=float(rpe)
        )


def describe(planned: PlannedSet) -> str:
    """The prescription as one short human phrase — for error messages that have to be specific.

    "A set needs a measurement" is true and useless when the caller is looking at a line that says
    8–10 reps at 60 kg. Saying which line, in the plan's own words, is the difference between an
    error a model can act on and one it has to guess at.
    """
    parts: list[str] = []
    if planned.target_reps_min is not None or planned.target_reps_max is not None:
        low, high = planned.target_reps_min, planned.target_reps_max
        if low is not None and high is not None:
            parts.append(f"{low} reps" if low == high else f"{low}-{high} reps")
        elif low is not None:
            parts.append(f"{low}+ reps")
        else:
            parts.append(f"up to {high} reps")
    if planned.target_hold_seconds is not None:
        parts.append(f"{planned.target_hold_seconds}s hold")
    if planned.target_weight_kg is not None:
        parts.append(f"@ {planned.target_weight_kg:g} kg")
    if planned.target_rpe is not None:
        parts.append(f"RPE {planned.target_rpe:g}")
    return " ".join(parts) if parts else "no explicit target"


async def _next_order_index(db: AsyncSession, session_id: uuid.UUID) -> int:
    """One past the highest position already prescribed for this session (0 when empty).

    Counts deleted rows too — deliberately. Reusing the position of a line you removed would put
    a restored row on top of a later one, and the ordering is the only thing that says what comes
    next.
    """
    highest = (
        await db.execute(
            select(func.max(PlannedSet.order_index)).where(PlannedSet.session_id == session_id)
        )
    ).scalar_one()
    return 0 if highest is None else int(highest) + 1


async def _ever_planned(db: AsyncSession, session_id: uuid.UUID) -> bool:
    """Whether this session has ever held a prescribed line, deleted ones included.

    The question :func:`plan_session` needs for its replay check — "did this call already run?" —
    which "does it hold one *now*?" answers wrongly for a plan someone has since edited down to
    nothing.
    """
    return (
        await db.execute(select(func.count()).where(PlannedSet.session_id == session_id))
    ).scalar_one() > 0


async def _existing_by_client_key(
    db: AsyncSession, user_id: uuid.UUID, client_key: str | None
) -> PlannedSet | None:
    """The planned row a previous call with this key already created, if any."""
    if client_key is None:
        return None
    return (
        await db.execute(
            select(PlannedSet).where(
                PlannedSet.user_id == user_id, PlannedSet.client_key == client_key
            )
        )
    ).scalar_one_or_none()


async def _items_for(db: AsyncSession, session_id: uuid.UUID) -> list[PlannedItem]:
    """The session's live prescription in reading order, each line with its live completion.

    One statement, one join: asking "is this done?" per row would be a query per prescribed set,
    and the join is also what guarantees a soft-deleted set never reads as a completion.
    """
    rows = (
        await db.execute(
            select(PlannedSet, ExerciseSet)
            .outerjoin(
                ExerciseSet,
                and_(
                    ExerciseSet.id == PlannedSet.completed_set_id,
                    ExerciseSet.deleted_at.is_(None),
                ),
            )
            .where(PlannedSet.session_id == session_id, PlannedSet.deleted_at.is_(None))
            .order_by(PlannedSet.order_index, PlannedSet.set_number, PlannedSet.id)
        )
    ).all()
    return [PlannedItem(planned=planned, completed_set=done) for planned, done in rows]


async def _exercises_for(
    db: AsyncSession, exercise_ids: set[uuid.UUID]
) -> dict[uuid.UUID, Exercise]:
    if not exercise_ids:
        return {}
    rows = (await db.execute(select(Exercise).where(Exercise.id.in_(exercise_ids)))).scalars().all()
    return {row.id: row for row in rows}


async def _logged_and_off_plan(db: AsyncSession, session_id: uuid.UUID) -> tuple[int, int]:
    """(live sets in the session, how many of them no live prescribed line claims).

    An anti-join rather than "logged minus completed": a set can be claimed by a line whose own
    session was changed underneath it, and subtraction would then report a negative surplus.
    """
    logged = (
        await db.execute(
            select(func.count()).where(
                ExerciseSet.session_id == session_id, ExerciseSet.deleted_at.is_(None)
            )
        )
    ).scalar_one()
    claimed = select(PlannedSet.id).where(
        PlannedSet.completed_set_id == ExerciseSet.id, PlannedSet.deleted_at.is_(None)
    )
    off_plan = (
        await db.execute(
            select(func.count())
            .select_from(ExerciseSet)
            .where(
                ExerciseSet.session_id == session_id,
                ExerciseSet.deleted_at.is_(None),
                ~claimed.exists(),
            )
        )
    ).scalar_one()
    return int(logged), int(off_plan)


def _adherence(items: Sequence[PlannedItem], off_plan_count: int) -> Adherence:
    planned_total = len(items)
    completed = sum(1 for item in items if item.is_completed)
    return Adherence(
        planned_total=planned_total,
        completed_count=completed,
        pending_count=planned_total - completed,
        off_plan_count=off_plan_count,
        percent=(None if planned_total == 0 else round(completed / planned_total * 100, 1)),
    )


# ── Counts (used by the session lifecycle, which must not pay for a full plan read) ───
async def counts(db: AsyncSession, *, session_id: uuid.UUID) -> tuple[int, int]:
    """``(planned_total, completed_count)`` for one session, in a single aggregate.

    ``get_active_session`` reports these on every screen that asks "am I training?", so it gets the
    two numbers without loading the prescription — the same reason ``set_count`` travels with the
    active session rather than being counted by fetching the whole detail.
    """
    planned_total, completed_count = (
        await db.execute(
            select(func.count(), func.count(ExerciseSet.id))
            .select_from(PlannedSet)
            .outerjoin(
                ExerciseSet,
                and_(
                    ExerciseSet.id == PlannedSet.completed_set_id,
                    ExerciseSet.deleted_at.is_(None),
                ),
            )
            .where(PlannedSet.session_id == session_id, PlannedSet.deleted_at.is_(None))
        )
    ).one()
    return int(planned_total), int(completed_count)


async def adherence(db: AsyncSession, *, session_id: uuid.UUID) -> Adherence:
    """What ``finish_session`` reports: how much of the plan was done, and what wasn't in it.

    Session ownership is the caller's business — every path that reaches here has already resolved
    the session as the user's own.
    """
    items = await _items_for(db, session_id)
    _logged, off_plan = await _logged_and_off_plan(db, session_id)
    return _adherence(items, off_plan)


# ── Writes ───────────────────────────────────────────────────────────────────────────
async def add_planned_sets(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    drafts: Sequence[PlannedSetDraft],
) -> list[PlannedSet]:
    """Append lines to a session's prescription, as one unit.

    All or nothing, for the same reason ``log_sets`` is: a plan that landed half-written is worse
    than one that never landed, because the missing half looks like a coach's decision.
    ``client_key`` per line makes a retry return the original rows instead of a second copy of the
    workout.

    **Every line is resolved and validated before any row is created.** Validating as it goes would
    leave the rejected call's earlier lines pending in the session, and the very next read would
    autoflush them — so "one bad line aborts the call" would depend on the caller's transaction
    being rolled back rather than on this function.
    """
    if not drafts:
        raise errors.validation("planned_sets must not be empty")
    await _owned_session(db, user_id, session_id)

    # Pass one: resolve replays, check visibility, reject anything that cannot be met. No writes.
    replays: dict[int, PlannedSet] = {}
    fresh: list[tuple[int, PlannedSetDraft]] = []
    seen_keys: dict[str, int] = {}
    for index, draft in enumerate(drafts):
        # Two lines in one call cannot share a key: the replay lookup runs before either is
        # written, so neither finds the other and both are created — straight into the partial
        # unique index, as a 500 rather than an answer. A key identifies one row, and inside a
        # single call the caller can see they have used it twice.
        if draft.client_key is not None:
            first = seen_keys.setdefault(draft.client_key, index)
            if first != index:
                raise errors.validation(
                    f"planned_sets[{index}]: client_key {draft.client_key!r} is already used by "
                    f"planned_sets[{first}] in this call — a key identifies one line",
                    client_key=draft.client_key,
                )
        replay = await _existing_by_client_key(db, user_id, draft.client_key)
        if replay is not None:
            replays[index] = replay
            continue
        await sets_service.assert_exercise_visible(db, user_id, draft.exercise_id)
        _validate_targets(
            reps_min=draft.target_reps_min,
            reps_max=draft.target_reps_max,
            weight_kg=_to_decimal(draft.target_weight_kg),
            rpe=_to_decimal(draft.target_rpe),
            hold_seconds=draft.target_hold_seconds,
            where=f"planned_sets[{index}]",
        )
        fresh.append((index, draft))

    # Pass two: write. Everything below is known good, so nothing can abort half way.
    position = await _next_order_index(db, session_id)
    order: dict[int, PlannedSet] = dict(replays)
    created: list[PlannedSet] = []
    for index, draft in fresh:
        planned = PlannedSet(
            user_id=user_id,
            session_id=session_id,
            exercise_id=draft.exercise_id,
            set_number=draft.set_number,
            order_index=position if draft.order_index is None else draft.order_index,
            target_reps_min=draft.target_reps_min,
            target_reps_max=draft.target_reps_max,
            target_weight_kg=_to_decimal(draft.target_weight_kg),
            target_rpe=_to_decimal(draft.target_rpe),
            target_hold_seconds=draft.target_hold_seconds,
            notes=draft.notes,
            client_key=draft.client_key,
        )
        position += 1
        db.add(planned)
        created.append(planned)
        order[index] = planned

    await db.flush()
    for planned in created:
        await db.refresh(planned)
    return [order[index] for index in range(len(drafts))]


async def plan_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    performed_at: datetime,
    drafts: Sequence[PlannedSetDraft],
    title: str | None = None,
    type: str | None = None,
    notes: str | None = None,
    client_key: str | None = None,
) -> PlannedSession:
    """Create a session **and** its prescription in one transaction.

    The session is an ordinary ``workout_sessions`` row — there is no separate "planned" table for
    sessions and no status column, because a plan is not a different kind of workout, it is a
    workout that has not happened yet. What makes it a plan is that it carries prescribed lines and
    no logged sets, and that is a question the data answers rather than a state something has to
    remember to update.

    Dated in the future, it stays out of ``get_active_session`` until its time arrives (see
    ``services/sessions.SCHEDULING_SKEW``); dated now, it is the session you are about to train.

    ``client_key`` covers the session; each line carries its own.
    """
    session = await sessions_service.create(
        db,
        user_id=user_id,
        performed_at=performed_at,
        title=title,
        type=type,
        notes=notes,
        client_key=client_key,
    )
    # A replayed `client_key` hands back the session that already exists, prescription and all, so
    # adding the lines again would write the workout twice. Asking whether this session has *ever*
    # held a prescribed line answers it — and it is the same question either way, because a freshly
    # created session has never held one.
    #
    # "Ever", not "currently": a plan whose lines were deleted one by one is a plan someone edited
    # down to nothing, and a retry landing on it would silently restore the whole workout they had
    # just taken apart.
    if not await _ever_planned(db, session.id):
        await add_planned_sets(db, user_id=user_id, session_id=session.id, drafts=drafts)
    return await get_plan(db, user_id=user_id, session_id=session.id)


async def update_planned_set(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    planned_set_id: uuid.UUID,
    changes: Mapping[str, Any],
    clear_notes: bool = False,
) -> PlannedSet:
    """Correct one line of a prescription. Only the supplied keys change.

    ``clear_notes`` for the same reason it exists everywhere else in this API: in a partial update
    ``null`` already means "leave alone", so emptying a field needs its own word.

    Editing a line that has already been completed is allowed and changes **nothing about the
    logged set**. The plan said one thing, the training was another; correcting the plan afterwards
    is bookkeeping about the prescription, and rewriting the log to match would be the one edit
    this module must never make.
    """
    planned = await _owned_planned(db, user_id, planned_set_id)
    for key, value in changes.items():
        if key not in _UPDATABLE:
            raise errors.validation(f"Field '{key}' is not updatable")
        if key in ("target_weight_kg", "target_rpe"):
            value = _to_decimal(value)
        setattr(planned, key, value)
    if clear_notes:
        planned.notes = None

    _validate_targets(
        reps_min=planned.target_reps_min,
        reps_max=planned.target_reps_max,
        weight_kg=planned.target_weight_kg,
        rpe=planned.target_rpe,
        hold_seconds=planned.target_hold_seconds,
    )
    await db.flush()
    await db.refresh(planned)
    return planned


async def delete_planned_set(
    db: AsyncSession, *, user_id: uuid.UUID, planned_set_id: uuid.UUID, at: datetime | None = None
) -> PlannedSet:
    """Remove one line from a prescription. Soft, and it never touches the log.

    A completed line can be deleted: the set stays exactly where it is and simply becomes off-plan
    work. Taking a line out of the plan is a statement about the plan, not a retraction of training
    that happened — deleting the set is ``delete_set``, and it is a different decision.
    """
    planned = await _owned_planned(db, user_id, planned_set_id)
    planned.deleted_at = at or clock.now()
    await db.flush()
    await db.refresh(planned)
    return planned


async def complete(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    planned_set_id: uuid.UUID,
    weight_kg: float | None = None,
    reps: int | None = None,
    hold_seconds: int | None = None,
    rpe: float | None = None,
    notes: str | None = None,
    is_backfill: bool = False,
    client_key: str | None = None,
) -> CompletedPlannedSet:
    """Log what was actually done against a prescribed line, and link the two.

    This is the **only** door between the plan and the data. It writes a real ``exercise_sets`` row
    through ``services/sets.log_set`` — the same function the log button and every other tool call —
    so PR detection, the ``client_key`` retry guard and the exercise/session ownership checks are
    the ones that already exist rather than a second implementation that can drift from them.

    What you did is **not** assumed from what was prescribed. A range of 8–10 has no single right
    answer, and a plan quietly recording its own targets as results would make adherence a tautology
    — the numbers would always agree with the plan because they *were* the plan. Pass what happened.

    ``client_key`` makes the call idempotent end to end: a retry returns the original set, its
    current PR verdict, and the same link.
    """
    planned = await _owned_planned(db, user_id, planned_set_id)

    standing = await _live_completion(db, planned)
    if standing is not None and not (client_key is not None and standing.client_key == client_key):
        raise errors.conflict(
            "That planned set is already completed. Correct what was logged with update_set, or "
            "delete_set first if it should not have been logged at all.",
            planned_set_id=str(planned.id),
            completed_set_id=str(standing.id),
        )

    if weight_kg is None and reps is None and hold_seconds is None:
        raise errors.validation(
            "Pass what you actually did — at least one of weight_kg, reps or hold_seconds. "
            f"This set is prescribed as: {describe(planned)}.",
            planned_set_id=str(planned.id),
        )

    logged = await sets_service.log_set(
        db,
        user_id=user_id,
        session_id=planned.session_id,
        exercise_id=planned.exercise_id,
        set_number=planned.set_number,
        weight_kg=weight_kg,
        reps=reps,
        hold_seconds=hold_seconds,
        rpe=rpe,
        notes=notes,
        is_backfill=is_backfill,
        client_key=client_key,
    )
    _assert_satisfies(planned, logged.set)

    claimant = await _claimant(db, logged.set.id)
    if claimant is not None and claimant.id != planned.id:
        raise errors.conflict(
            "That set already completes a different planned set.",
            set_id=str(logged.set.id),
            planned_set_id=str(claimant.id),
        )

    planned.completed_set_id = logged.set.id
    await db.flush()
    await db.refresh(planned)
    return CompletedPlannedSet(
        item=PlannedItem(planned=planned, completed_set=logged.set), logged=logged
    )


def _assert_satisfies(planned: PlannedSet, logged: ExerciseSet) -> None:
    """Refuse a set that cannot be what this line asked for.

    Only reachable through ``client_key``. ``sets.log_set`` resolves a replay on ``(user_id,
    client_key)`` **alone** and returns before it checks the session or the exercise it was
    handed — correctly, since a replay is meant to hand back the row the first call made. But that
    means a key already used elsewhere hands ``complete`` a set from another session, another
    movement, or one that has since been deleted, and linking it would claim adherence for training
    that is not in this workout at all. A reused key is the caller's mistake to hear about, not
    something to quietly absorb.
    """
    if logged.deleted_at is not None:
        raise errors.conflict(
            "That client_key belongs to a set that has since been deleted. Use a new key, or "
            "restore the set if it should not have been removed.",
            planned_set_id=str(planned.id),
            set_id=str(logged.id),
        )
    if logged.session_id != planned.session_id or logged.exercise_id != planned.exercise_id:
        raise errors.conflict(
            "That client_key already belongs to a different set — a client_key is unique per "
            "user, not per session. Use a key you have not used before.",
            planned_set_id=str(planned.id),
            set_id=str(logged.id),
        )


async def _live_completion(db: AsyncSession, planned: PlannedSet) -> ExerciseSet | None:
    """The live set completing this line, or ``None`` — including when the link points at a
    deleted one, which is exactly how a deleted set reopens the prescription."""
    if planned.completed_set_id is None:
        return None
    return (
        await db.execute(
            select(ExerciseSet).where(
                ExerciseSet.id == planned.completed_set_id, ExerciseSet.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()


async def _claimant(db: AsyncSession, set_id: uuid.UUID) -> PlannedSet | None:
    """The live prescribed line already pointing at this set, if any."""
    return (
        await db.execute(
            select(PlannedSet).where(
                PlannedSet.completed_set_id == set_id, PlannedSet.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()


# ── Reads ────────────────────────────────────────────────────────────────────────────
async def get_plan(
    db: AsyncSession, *, user_id: uuid.UUID, session_id: uuid.UUID
) -> PlannedSession:
    """A session's prescription in reading order, each line with its completion state.

    Flat and ordered rather than grouped by exercise, because the order *is* the prescription: a
    superset reads A1, B1, A2, B2, and grouping by movement would silently rewrite it into two
    straight sets of each.
    """
    session = await _owned_session(db, user_id, session_id)
    items = await _items_for(db, session_id)
    exercises = await _exercises_for(db, {item.planned.exercise_id for item in items})
    return PlannedSession(session=session, items=items, exercises=exercises)


async def progress(
    db: AsyncSession, *, user_id: uuid.UUID, session_id: uuid.UUID
) -> SessionProgress:
    """Planned vs done for one session: the counts, the per-movement breakdown, and what is next.

    Works on a session with no plan at all — everything logged is simply off-plan and ``next_up``
    is ``None``. "Nothing was prescribed" is a legitimate answer to "how am I doing?", and a
    404 there would make the tool unusable on ordinary workouts.
    """
    session = await _owned_session(db, user_id, session_id)
    items = await _items_for(db, session_id)
    logged_total, off_plan = await _logged_and_off_plan(db, session_id)
    exercises = await _exercises_for(db, {item.planned.exercise_id for item in items})

    tally: dict[uuid.UUID, list[int]] = {}
    for item in items:
        counts_for = tally.setdefault(item.planned.exercise_id, [0, 0])
        counts_for[0] += 1
        counts_for[1] += 1 if item.is_completed else 0

    # Ordered by where each movement first appears in the plan, not alphabetically — the answer to
    # "what is left?" should read in the order you are meant to do it.
    first_seen: dict[uuid.UUID, int] = {}
    for position, item in enumerate(items):
        first_seen.setdefault(item.planned.exercise_id, position)

    breakdown = [
        ExerciseProgress(exercise=exercises[exercise_id], planned=planned, completed=done)
        for exercise_id, (planned, done) in sorted(
            tally.items(), key=lambda entry: first_seen[entry[0]]
        )
        if exercise_id in exercises
    ]
    next_up = next((item for item in items if not item.is_completed), None)

    return SessionProgress(
        session=session,
        adherence=_adherence(items, off_plan),
        logged_total=logged_total,
        exercises=breakdown,
        next_up=next_up,
    )


# ── Cascades (called by the session lifecycle) ───────────────────────────────────────
async def soft_delete_for_session(db: AsyncSession, *, session_id: uuid.UUID, at: datetime) -> int:
    """Remove a session's prescription along with the session, and say how many lines went.

    Unconditional, unlike the sets cascade: a prescription cannot exist without the session it
    prescribes, so there is no version of "keep the plan, drop the workout" worth offering. The
    ``cascade`` flag on ``sessions.delete`` guards *logged training*, which is the thing you might
    reasonably want to keep.
    """
    rows = (
        (
            await db.execute(
                select(PlannedSet).where(
                    PlannedSet.session_id == session_id, PlannedSet.deleted_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.deleted_at = at
    if rows:
        await db.flush()
    return len(rows)


async def restore_for_session(db: AsyncSession, *, session_id: uuid.UUID, at: datetime) -> int:
    """Bring back the prescription deleted *with* a session — matched on the delete's timestamp.

    The same rule ``restore`` uses for sets: lines removed separately beforehand stay removed,
    because restoring a session should undo one delete, not every edit the plan ever had.
    """
    rows = (
        (
            await db.execute(
                select(PlannedSet).where(
                    PlannedSet.session_id == session_id, PlannedSet.deleted_at == at
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        await reopen_if_claim_taken(db, row)
        row.deleted_at = None
    if rows:
        await db.flush()
    return len(rows)


async def reopen_if_claim_taken(db: AsyncSession, planned: PlannedSet) -> bool:
    """Drop a **deleted** line's claim on a set that another live line has since taken.

    Called immediately before ``restore`` clears ``deleted_at``, and it is not optional. A deleted
    line releases its set — that is what the partial unique index means — so the set can legally be
    completed against a different line while this one is gone. Un-deleting it then puts two live
    rows in the index and Postgres refuses the ``UPDATE`` with a unique violation, which reaches the
    caller as a 500 on *the undo*: the one operation that has to work.

    The line comes back **outstanding** instead, which is simply what is true — the set it used to
    name belongs to another line now, and the plan is a line short of done again. Returns whether a
    claim was released, so a caller can say so.
    """
    if planned.completed_set_id is None:
        return False
    taken = (
        await db.execute(
            select(PlannedSet.id).where(
                PlannedSet.completed_set_id == planned.completed_set_id,
                PlannedSet.deleted_at.is_(None),
                PlannedSet.id != planned.id,
            )
        )
    ).first()
    if taken is None:
        return False
    planned.completed_set_id = None
    return True
