"""PR read service: listing with exercise join + PR-set history."""

from __future__ import annotations

from app.services import prs, sets
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_global_exercise, make_session, make_user


async def test_list_and_history(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    exercise = await make_global_exercise(db_session, slug="bench", name="Bench")
    session = await make_session(db_session, user_id=user.id)

    await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=1,
        weight_kg=100,
        reps=5,
    )
    await sets.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=exercise.id,
        set_number=2,
        weight_kg=110,
        reps=5,
    )

    listed = await prs.list_prs(db_session, user_id=user.id)
    assert len(listed) == 1
    assert listed[0].exercise.name == "Bench"
    assert listed[0].pr.pr_type == "weight"
    assert listed[0].pr.value == 110

    history = await prs.history(
        db_session, user_id=user.id, exercise_id=exercise.id, pr_type="weight"
    )
    # Both weight PRs (100 then 110) are recorded chronologically.
    assert [s.weight_kg for s in history] == [100, 110]


async def test_list_scoped_to_user(db_session: AsyncSession) -> None:
    alice = await make_user(db_session, email="alice@example.com")
    bob = await make_user(db_session, email="bob@example.com")
    exercise = await make_global_exercise(db_session)
    bob_session = await make_session(db_session, user_id=bob.id)
    await sets.log_set(
        db_session,
        user_id=bob.id,
        session_id=bob_session.id,
        exercise_id=exercise.id,
        set_number=1,
        weight_kg=80,
        reps=5,
    )

    assert await prs.list_prs(db_session, user_id=alice.id) == []
