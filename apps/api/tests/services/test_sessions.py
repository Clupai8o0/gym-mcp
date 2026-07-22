"""Session service: CRUD, detail-with-sets, and ownership scoping."""

from __future__ import annotations

from datetime import UTC, datetime

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
