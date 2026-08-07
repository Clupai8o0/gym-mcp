"""Analytics service: volume tonnage rules + weekly frequency bucketing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services import analytics, sessions, sets
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_global_exercise, make_session, make_user

_REF = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


async def test_volume_tonnage_and_bodyweight(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    weighted = await make_global_exercise(db_session, slug="press", name="Press")
    bodyweight = await make_global_exercise(db_session, slug="pushup", name="Push Up")
    session = await make_session(db_session, user_id=user.id, performed_at=_REF)

    for n in (1, 2):
        await sets.log_set(
            db_session,
            user_id=user.id,
            session_id=session.id,
            exercise_id=weighted.id,
            set_number=n,
            weight_kg=100,
            reps=5,
        )
    await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=bodyweight.id,
        set_number=1,
        reps=20,
    )

    buckets = {
        b.exercise_name: b
        for b in await analytics.volume(
            db_session,
            user_id=user.id,
            date_from=_REF - timedelta(days=1),
            date_to=_REF + timedelta(days=1),
        )
    }

    assert buckets["Press"].total_sets == 2
    assert buckets["Press"].total_reps == 10
    assert buckets["Press"].total_tonnage_kg == 1000.0
    # A bodyweight set makes tonnage unknowable → None (not a partial sum).
    assert buckets["Push Up"].total_tonnage_kg is None
    assert buckets["Push Up"].total_reps == 20


async def test_volume_rejects_reversed_range(db_session: AsyncSession) -> None:
    from app.core.errors import ServiceError

    user = await make_user(db_session)
    try:
        await analytics.volume(
            db_session, user_id=user.id, date_from=_REF, date_to=_REF - timedelta(days=1)
        )
    except ServiceError as exc:
        assert exc.kind.value == "validation"
    else:  # pragma: no cover
        raise AssertionError("expected a validation ServiceError")


async def test_frequency_buckets(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    now = datetime(2026, 6, 17, 9, 0, tzinfo=UTC)  # a Wednesday

    await make_session(db_session, user_id=user.id, performed_at=now)
    await make_session(db_session, user_id=user.id, performed_at=now - timedelta(hours=2))
    await make_session(db_session, user_id=user.id, performed_at=now - timedelta(days=14))
    # Outside the 4-week window — must be excluded.
    await make_session(db_session, user_id=user.id, performed_at=now - timedelta(days=60))

    result = await analytics.frequency(db_session, user_id=user.id, weeks=4, now=now)

    assert len(result) == 4  # zero-filled to exactly N weeks
    assert result[-1].count == 2  # current week (buckets sorted ascending)
    assert sum(w.count for w in result) == 3  # the 60-day-old session is excluded


async def test_a_deleted_session_leaves_the_totals(db_session: AsyncSession) -> None:
    """Deleting a session takes it out of the data, not just out of the list — otherwise its
    tonnage stayed in every total forever and nothing could take it back."""
    user = await make_user(db_session)
    exercise = await make_global_exercise(db_session, slug="press", name="Press")
    session = await make_session(db_session, user_id=user.id, performed_at=_REF)
    await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=1,
        weight_kg=100,
        reps=5,
    )

    frm, to = _REF - timedelta(days=1), _REF + timedelta(days=1)
    assert len(await analytics.volume(db_session, user_id=user.id, date_from=frm, date_to=to)) == 1
    assert sum(w.count for w in await analytics.frequency(db_session, user_id=user.id, now=_REF))

    await sessions.delete(db_session, user_id=user.id, session_id=session.id)

    assert await analytics.volume(db_session, user_id=user.id, date_from=frm, date_to=to) == []
    assert not sum(
        w.count for w in await analytics.frequency(db_session, user_id=user.id, now=_REF)
    )


async def test_a_deleted_set_leaves_the_tonnage(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    exercise = await make_global_exercise(db_session, slug="squat", name="Squat")
    session = await make_session(db_session, user_id=user.id, performed_at=_REF)
    kept = await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=1,
        weight_kg=100,
        reps=5,
    )
    removed = await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=2,
        weight_kg=100,
        reps=5,
    )
    await sets.delete_set(db_session, user_id=user.id, set_id=removed.set.id)

    buckets = await analytics.volume(
        db_session,
        user_id=user.id,
        date_from=_REF - timedelta(days=1),
        date_to=_REF + timedelta(days=1),
    )
    assert len(buckets) == 1
    assert buckets[0].total_sets == 1 and buckets[0].total_tonnage_kg == 500.0
    assert kept.set.deleted_at is None
