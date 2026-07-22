"""PR-detection unit tests — the domain contract in ``services/sets`` (docs/03 acceptance).

Sets logged into a single session share a ``performed_at``; the recompute then orders by
``set_number``, so increasing set numbers give a deterministic chronology.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.models import PersonalRecord
from app.services import sets
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_global_exercise, make_session, make_user


async def _records(
    db: AsyncSession, user_id: uuid.UUID, exercise_id: uuid.UUID
) -> dict[str, Decimal]:
    rows = (
        (
            await db.execute(
                select(PersonalRecord).where(
                    PersonalRecord.user_id == user_id,
                    PersonalRecord.exercise_id == exercise_id,
                )
            )
        )
        .scalars()
        .all()
    )
    return {r.pr_type: r.value for r in rows}


async def _fixture(db: AsyncSession, slug: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    user = await make_user(db, email=f"{slug}@example.com")
    exercise = await make_global_exercise(db, slug=slug, name=slug)
    session = await make_session(db, user_id=user.id)
    return user.id, exercise.id, session.id


async def _log(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    exercise_id: uuid.UUID,
    set_number: int,
    **metrics: object,
) -> sets.LoggedSet:
    return await sets.log_set(
        db,
        user_id=user_id,
        session_id=session_id,
        exercise_id=exercise_id,
        set_number=set_number,
        **metrics,  # type: ignore[arg-type]
    )


async def test_first_log_bodyweight_reps(db_session: AsyncSession) -> None:
    user_id, exercise_id, session_id = await _fixture(db_session, "pullup")

    logged = await _log(db_session, user_id, session_id, exercise_id, 1, reps=10)

    assert logged.pr.is_pr is True
    assert logged.pr.pr_type == "first_log"
    assert logged.pr.previous_best is None
    assert logged.pr.new_value == Decimal(10)
    # first_log collapses to the concrete 'reps' metric for the stored record.
    assert await _records(db_session, user_id, exercise_id) == {"reps": Decimal(10)}


async def test_weight_then_reps_pr_progression(db_session: AsyncSession) -> None:
    user_id, exercise_id, session_id = await _fixture(db_session, "bench")

    first = await _log(db_session, user_id, session_id, exercise_id, 1, weight_kg=100, reps=5)
    assert first.pr.pr_type == "weight"  # weight+reps beats first_log by priority

    more_reps = await _log(db_session, user_id, session_id, exercise_id, 2, weight_kg=100, reps=8)
    assert more_reps.pr.pr_type == "reps"
    assert more_reps.pr.previous_best is None
    assert more_reps.pr.new_value == Decimal(8)

    heavier = await _log(db_session, user_id, session_id, exercise_id, 3, weight_kg=110, reps=3)
    assert heavier.pr.pr_type == "weight"
    assert heavier.pr.previous_best == Decimal(100)
    assert heavier.pr.new_value == Decimal(110)

    no_pr = await _log(db_session, user_id, session_id, exercise_id, 4, weight_kg=105, reps=3)
    assert no_pr.pr.is_pr is False
    assert no_pr.pr.pr_type is None

    assert await _records(db_session, user_id, exercise_id) == {
        "weight": Decimal(110),
        "reps": Decimal(8),
    }


async def test_hold_time_pr(db_session: AsyncSession) -> None:
    user_id, exercise_id, session_id = await _fixture(db_session, "plank")

    first = await _log(db_session, user_id, session_id, exercise_id, 1, hold_seconds=30)
    assert first.pr.pr_type == "hold_time"

    shorter = await _log(db_session, user_id, session_id, exercise_id, 2, hold_seconds=25)
    assert shorter.pr.is_pr is False

    longer = await _log(db_session, user_id, session_id, exercise_id, 3, hold_seconds=45)
    assert longer.pr.pr_type == "hold_time"
    assert longer.pr.previous_best == Decimal(30)

    assert await _records(db_session, user_id, exercise_id) == {"hold_time": Decimal(45)}


async def test_weight_only_never_beats_after_first_log(db_session: AsyncSession) -> None:
    """A heavier weight-only set is not a weight PR (weight PRs require reps) — legacy contract."""
    user_id, exercise_id, session_id = await _fixture(db_session, "farmer-carry")

    first = await _log(db_session, user_id, session_id, exercise_id, 1, weight_kg=100)
    assert first.pr.pr_type == "first_log"

    heavier = await _log(db_session, user_id, session_id, exercise_id, 2, weight_kg=120)
    assert heavier.pr.is_pr is False

    assert await _records(db_session, user_id, exercise_id) == {"weight": Decimal(100)}


async def test_update_set_recomputes_and_lowers_pr(db_session: AsyncSession) -> None:
    user_id, exercise_id, session_id = await _fixture(db_session, "squat")

    await _log(db_session, user_id, session_id, exercise_id, 1, weight_kg=100, reps=5)
    top = await _log(db_session, user_id, session_id, exercise_id, 2, weight_kg=110, reps=5)
    assert (await _records(db_session, user_id, exercise_id))["weight"] == Decimal(110)

    # Edit the top set down; the weight PR must fall back to the remaining best (100).
    await sets.update_set(
        db_session, user_id=user_id, set_id=top.set.id, changes={"weight_kg": 100.0}
    )
    assert (await _records(db_session, user_id, exercise_id))["weight"] == Decimal(100)


async def test_delete_set_recomputes(db_session: AsyncSession) -> None:
    user_id, exercise_id, session_id = await _fixture(db_session, "deadlift")

    top = await _log(db_session, user_id, session_id, exercise_id, 1, weight_kg=140, reps=5)
    await _log(db_session, user_id, session_id, exercise_id, 2, weight_kg=100, reps=6)
    assert (await _records(db_session, user_id, exercise_id))["weight"] == Decimal(140)

    await sets.delete_set(db_session, user_id=user_id, set_id=top.set.id)
    records = await _records(db_session, user_id, exercise_id)
    assert records["weight"] == Decimal(100)  # recomputed from the remaining set


async def test_log_set_requires_a_measurement(db_session: AsyncSession) -> None:
    from app.core.errors import ServiceError

    user_id, exercise_id, session_id = await _fixture(db_session, "curl")
    try:
        await _log(db_session, user_id, session_id, exercise_id, 1, rpe=8)
    except ServiceError as exc:
        assert exc.kind.value == "validation"
    else:  # pragma: no cover
        raise AssertionError("expected a validation ServiceError")


async def test_log_set_rejects_foreign_session(db_session: AsyncSession) -> None:
    from app.core.errors import ServiceError

    owner_id, exercise_id, session_id = await _fixture(db_session, "row")
    intruder = await make_user(db_session, email="intruder@example.com")

    try:
        await sets.log_set(
            db_session,
            user_id=intruder.id,
            session_id=session_id,  # belongs to owner, not intruder
            exercise_id=exercise_id,
            set_number=1,
            reps=5,
        )
    except ServiceError as exc:
        assert exc.kind.value == "not_found"
    else:  # pragma: no cover
        raise AssertionError("expected a not_found ServiceError")
