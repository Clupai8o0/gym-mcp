"""Session service: CRUD, detail-with-sets, ownership scoping, and the lifecycle (11A)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.core.errors import ServiceError
from app.models import WorkoutSession
from app.services import sessions, sets
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_global_exercise, make_session, make_user


async def test_create_and_get_with_sets(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    exercise = await make_global_exercise(db_session)
    session = await sessions.create(
        db_session, user_id=user.id, performed_at=datetime.now(tz=UTC), title="Upper"
    )
    await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=1,
        weight_kg=60,
        reps=5,
    )

    detail = await sessions.get(db_session, user_id=user.id, session_id=session.id)
    assert detail.session.title == "Upper"
    assert len(detail.sets) == 1
    assert exercise.id in detail.exercises


async def test_update_changes_only_supplied_fields(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    session = await make_session(db_session, user_id=user.id, title="Old", type="upper")

    updated = await sessions.update(
        db_session, user_id=user.id, session_id=session.id, changes={"title": "New"}
    )
    assert updated.title == "New"
    assert updated.type == "upper"  # untouched


async def test_delete_cascades_sets(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    exercise = await make_global_exercise(db_session)
    session = await make_session(db_session, user_id=user.id)
    await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=1,
        reps=5,
    )

    await sessions.delete(db_session, user_id=user.id, session_id=session.id)

    remaining = (
        await db_session.execute(select(WorkoutSession).where(WorkoutSession.id == session.id))
    ).scalar_one_or_none()
    assert remaining is None


async def test_list_filters_by_type(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await make_session(db_session, user_id=user.id, type="push")
    await make_session(db_session, user_id=user.id, type="pull")

    rows, total = await sessions.list_sessions(db_session, user_id=user.id, type="push")
    assert total == 1
    assert rows[0].type == "push"


async def test_get_foreign_session_is_not_found(db_session: AsyncSession) -> None:
    alice = await make_user(db_session, email="alice@example.com")
    bob = await make_user(db_session, email="bob@example.com")
    bob_session = await make_session(db_session, user_id=bob.id)

    with pytest.raises(ServiceError) as exc:
        await sessions.get(db_session, user_id=alice.id, session_id=bob_session.id)
    assert exc.value.kind.value == "not_found"


# ── Lifecycle (Phase 11A) ────────────────────────────────────────────────────────────
async def test_finish_stamps_ended_at_and_duration(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    started = datetime(2026, 7, 30, 17, 0, tzinfo=UTC)
    session = await make_session(db_session, user_id=user.id, performed_at=started)
    assert session.ended_at is None and session.duration_minutes is None

    finished = await sessions.finish_session(
        db_session,
        user_id=user.id,
        session_id=session.id,
        ended_at=started + timedelta(minutes=47),
    )
    assert finished.ended_at == started + timedelta(minutes=47)
    assert finished.duration_minutes == 47


async def test_finish_is_idempotent(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    started = datetime(2026, 7, 30, 17, 0, tzinfo=UTC)
    session = await make_session(db_session, user_id=user.id, performed_at=started)

    first = await sessions.finish_session(
        db_session, user_id=user.id, session_id=session.id, ended_at=started + timedelta(minutes=30)
    )
    # A second finish (double-tap, retried offline write) must not move the clock or raise.
    second = await sessions.finish_session(
        db_session, user_id=user.id, session_id=session.id, ended_at=started + timedelta(hours=5)
    )
    assert second.ended_at == first.ended_at
    assert second.duration_minutes == 30


async def test_finish_someone_elses_session_is_not_found(db_session: AsyncSession) -> None:
    alice = await make_user(db_session, email="alice@example.com")
    bob = await make_user(db_session, email="bob@example.com")
    bob_session = await make_session(db_session, user_id=bob.id)

    with pytest.raises(ServiceError) as exc:
        await sessions.finish_session(db_session, user_id=alice.id, session_id=bob_session.id)
    assert exc.value.kind.value == "not_found"

    await db_session.refresh(bob_session)
    assert bob_session.ended_at is None  # untouched


async def test_active_session_is_the_newest_unfinished_one(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    now = datetime.now(tz=UTC)
    await make_session(db_session, user_id=user.id, performed_at=now - timedelta(hours=2))
    newest = await make_session(
        db_session, user_id=user.id, performed_at=now - timedelta(minutes=5)
    )

    active = await sessions.get_active_session(db_session, user_id=user.id)
    assert active is not None and active.id == newest.id


async def test_active_session_is_none_once_finished(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    session = await make_session(db_session, user_id=user.id, performed_at=datetime.now(tz=UTC))

    assert await sessions.get_active_session(db_session, user_id=user.id) is not None
    await sessions.finish_session(db_session, user_id=user.id, session_id=session.id)
    assert await sessions.get_active_session(db_session, user_id=user.id) is None


async def test_active_session_is_scoped_to_the_user(db_session: AsyncSession) -> None:
    alice = await make_user(db_session, email="alice@example.com")
    bob = await make_user(db_session, email="bob@example.com")
    await make_session(db_session, user_id=bob.id, performed_at=datetime.now(tz=UTC))

    assert await sessions.get_active_session(db_session, user_id=alice.id) is None


async def test_dangling_session_is_auto_finished_from_its_last_set(
    db_session: AsyncSession,
) -> None:
    """A session left open overnight is retired on read, dated from its last set — not 'now'."""
    user = await make_user(db_session)
    exercise = await make_global_exercise(db_session)
    started = datetime.now(tz=UTC) - timedelta(minutes=90)
    session = await make_session(db_session, user_id=user.id, performed_at=started)
    logged = await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=1,
        weight_kg=60,
        reps=5,
    )

    # Read it 13 h later: past STALE_AFTER, so it is finished as of the set's timestamp.
    later = datetime.now(tz=UTC) + timedelta(hours=13)
    assert await sessions.get_active_session(db_session, user_id=user.id, now=later) is None

    await db_session.refresh(session)
    assert session.ended_at == logged.set.created_at
    # Duration covers the training, not the hours it sat forgotten.
    assert session.duration_minutes is not None and session.duration_minutes <= 91


async def test_dangling_session_without_sets_falls_back_to_its_start(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)
    started = datetime.now(tz=UTC)
    session = await make_session(db_session, user_id=user.id, performed_at=started)

    later = started + timedelta(hours=13)
    assert await sessions.get_active_session(db_session, user_id=user.id, now=later) is None

    await db_session.refresh(session)
    assert session.ended_at == started
    assert session.duration_minutes == 0


async def test_fresh_session_survives_the_staleness_sweep(db_session: AsyncSession) -> None:
    """The 12 h rule must never fire mid-workout — an 11 h-old session is still active."""
    user = await make_user(db_session)
    started = datetime.now(tz=UTC)
    session = await make_session(db_session, user_id=user.id, performed_at=started)

    active = await sessions.get_active_session(
        db_session, user_id=user.id, now=started + timedelta(hours=11)
    )
    assert active is not None and active.id == session.id


async def test_sweep_retires_older_dangling_sessions_but_keeps_the_live_one(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)
    now = datetime.now(tz=UTC)
    abandoned = await make_session(
        db_session, user_id=user.id, performed_at=now - timedelta(days=3)
    )
    live = await make_session(db_session, user_id=user.id, performed_at=now - timedelta(minutes=10))

    active = await sessions.get_active_session(db_session, user_id=user.id, now=now)
    assert active is not None and active.id == live.id

    await db_session.refresh(abandoned)
    assert abandoned.ended_at is not None  # swept, even though it wasn't the newest
