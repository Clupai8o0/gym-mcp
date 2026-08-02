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
    assert active is not None and active.session.id == newest.id


async def test_active_session_carries_its_set_count(db_session: AsyncSession) -> None:
    """The count travels with the session so a caller never fetches the whole detail to get it."""
    user = await make_user(db_session)
    exercise = await make_global_exercise(db_session)
    session = await make_session(db_session, user_id=user.id, performed_at=datetime.now(tz=UTC))

    empty = await sessions.get_active_session(db_session, user_id=user.id)
    assert empty is not None and empty.set_count == 0

    for number in (1, 2, 3):
        await sets.log_set(
            db_session,
            user_id=user.id,
            session_id=session.id,
            exercise_id=exercise.id,
            set_number=number,
            weight_kg=60,
            reps=5,
        )

    active = await sessions.get_active_session(db_session, user_id=user.id)
    assert active is not None and active.set_count == 3


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
    assert active is not None and active.session.id == session.id


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
    assert active is not None and active.session.id == live.id

    await db_session.refresh(abandoned)
    assert abandoned.ended_at is not None  # swept, even though it wasn't the newest


# ── Lifecycle: backdating, duration ownership, and post-hoc correction ────────────────────
class TestBackdatedSessionsAreBornFinished:
    """`log_session` used to leave `ended_at` null whatever it was handed, so recording last
    Tuesday's workout made it "in progress" and the session bar offered to resume it."""

    async def test_a_session_started_now_stays_open(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session)
        session = await sessions.create(
            db_session, user_id=user.id, performed_at=datetime.now(tz=UTC)
        )
        assert session.ended_at is None

    async def test_a_backdated_session_is_closed_at_its_start(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)
        performed = datetime.now(tz=UTC) - timedelta(days=90)
        session = await sessions.create(db_session, user_id=user.id, performed_at=performed)
        assert session.ended_at == performed
        assert await sessions.get_active_session(db_session, user_id=user.id) is None

    async def test_a_stated_duration_closes_the_session_arithmetically(
        self, db_session: AsyncSession
    ) -> None:
        """Even for a workout that started minutes ago: a duration means it is already over."""
        user = await make_user(db_session)
        performed = datetime.now(tz=UTC) - timedelta(minutes=10)
        session = await sessions.create(
            db_session, user_id=user.id, performed_at=performed, duration_minutes=45
        )
        assert session.ended_at == performed + timedelta(minutes=45)
        assert session.duration_minutes == 45
        assert await sessions.get_active_session(db_session, user_id=user.id) is None

    async def test_the_window_is_rolling_not_a_calendar_day(self, db_session: AsyncSession) -> None:
        """A workout started 6 h ago is live wherever the server is — no "is it today?"."""
        user = await make_user(db_session)
        session = await sessions.create(
            db_session, user_id=user.id, performed_at=datetime.now(tz=UTC) - timedelta(hours=6)
        )
        assert session.ended_at is None
        active = await sessions.get_active_session(db_session, user_id=user.id)
        assert active is not None and active.session.id == session.id

    async def test_an_old_open_session_is_never_active_even_if_recently_touched(
        self, db_session: AsyncSession
    ) -> None:
        """Rows created before the fix: adding a set kept resetting the last-activity clock."""
        user = await make_user(db_session)
        stale = WorkoutSession(
            user_id=user.id, performed_at=datetime.now(tz=UTC) - timedelta(days=90)
        )
        db_session.add(stale)
        await db_session.flush()

        assert await sessions.get_active_session(db_session, user_id=user.id) is None
        await db_session.refresh(stale)
        assert stale.ended_at is not None, "and it is retired, not left dangling"


class TestDurationOwnership:
    """`finish_session` recomputed `duration_minutes` as (now - performed_at), overwriting a
    value the caller had explicitly passed to `log_session`."""

    async def test_an_explicit_duration_survives_finish(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session)
        session = await sessions.create(
            db_session,
            user_id=user.id,
            performed_at=datetime.now(tz=UTC) - timedelta(days=3),
            duration_minutes=52,
        )
        # It is already finished, so this is a no-op — but force the path explicitly too.
        session.ended_at = None
        await db_session.flush()
        finished = await sessions.finish_session(db_session, user_id=user.id, session_id=session.id)
        assert finished.duration_minutes == 52, "the caller's own number, not wall-clock"
        assert finished.ended_at is not None

    async def test_a_derived_duration_is_clamped(self, db_session: AsyncSession) -> None:
        """A session left open for days would otherwise record 136,070 minutes."""
        user = await make_user(db_session)
        session = WorkoutSession(
            user_id=user.id, performed_at=datetime.now(tz=UTC) - timedelta(days=94)
        )
        db_session.add(session)
        await db_session.flush()

        finished = await sessions.finish_session(db_session, user_id=user.id, session_id=session.id)
        ceiling = int(sessions.MAX_DERIVED_DURATION.total_seconds() // 60)
        assert finished.duration_minutes == ceiling

    async def test_a_normal_derived_duration_is_untouched(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session)
        started = datetime.now(tz=UTC) - timedelta(minutes=75)
        session = await sessions.create(db_session, user_id=user.id, performed_at=started)
        finished = await sessions.finish_session(db_session, user_id=user.id, session_id=session.id)
        assert 74 <= (finished.duration_minutes or 0) <= 76


class TestUpdateRepairsASession:
    """Correcting a session after the fact is what stops any of this being permanent."""

    async def test_fixing_the_duration_moves_the_end_time(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session)
        performed = datetime.now(tz=UTC) - timedelta(days=2)
        session = await sessions.create(
            db_session, user_id=user.id, performed_at=performed, duration_minutes=600
        )
        fixed = await sessions.update(
            db_session,
            user_id=user.id,
            session_id=session.id,
            changes={"duration_minutes": 60},
        )
        assert fixed.duration_minutes == 60
        assert fixed.ended_at == performed + timedelta(minutes=60)

    async def test_moving_the_date_carries_the_end_time_with_it(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)
        session = await sessions.create(
            db_session,
            user_id=user.id,
            performed_at=datetime.now(tz=UTC) - timedelta(days=2),
            duration_minutes=45,
        )
        moved_to = datetime.now(tz=UTC) - timedelta(days=9)
        fixed = await sessions.update(
            db_session, user_id=user.id, session_id=session.id, changes={"performed_at": moved_to}
        )
        assert fixed.performed_at == moved_to
        assert fixed.ended_at == moved_to + timedelta(minutes=45)

    async def test_an_in_progress_session_keeps_its_null_end(
        self, db_session: AsyncSession
    ) -> None:
        user = await make_user(db_session)
        session = await sessions.create(
            db_session, user_id=user.id, performed_at=datetime.now(tz=UTC)
        )
        fixed = await sessions.update(
            db_session, user_id=user.id, session_id=session.id, changes={"title": "Push day"}
        )
        assert fixed.title == "Push day"
        assert fixed.ended_at is None, "it ends when it ends"
