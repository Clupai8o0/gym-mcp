"""Exercise service: visibility scoping, filters, and custom creation."""

from __future__ import annotations

import pytest
from app.core.errors import ServiceError
from app.services import exercises
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_custom_exercise, make_global_exercise, make_user


async def test_list_scopes_to_global_plus_own_customs(db_session: AsyncSession) -> None:
    alice = await make_user(db_session, email="alice@example.com")
    bob = await make_user(db_session, email="bob@example.com")
    await make_global_exercise(db_session, slug="bench-press", name="Bench Press")
    await make_custom_exercise(db_session, user_id=alice.id, slug="alice-move", name="Alice Move")
    await make_custom_exercise(db_session, user_id=bob.id, slug="bob-move", name="Bob Move")

    rows, total = await exercises.list_exercises(db_session, user_id=alice.id)
    names = {e.name for e in rows}

    assert total == 2
    assert names == {"Bench Press", "Alice Move"}
    assert "Bob Move" not in names  # another user's custom is invisible


async def test_list_filters(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    barbell = await make_global_exercise(db_session, slug="squat", name="Back Squat")
    barbell.category = "strength"
    barbell.equipment = "barbell"
    barbell.level = "intermediate"
    barbell.primary_muscles = ["quadriceps"]
    stretch = await make_global_exercise(db_session, slug="hamstring", name="Hamstring Stretch")
    stretch.category = "stretching"
    await db_session.flush()

    by_cat, total = await exercises.list_exercises(
        db_session, user_id=user.id, category="stretching"
    )
    assert [e.name for e in by_cat] == ["Hamstring Stretch"]

    by_muscle, _ = await exercises.list_exercises(db_session, user_id=user.id, muscle="quadriceps")
    assert [e.name for e in by_muscle] == ["Back Squat"]

    by_q, _ = await exercises.list_exercises(db_session, user_id=user.id, q="squat")
    assert [e.name for e in by_q] == ["Back Squat"]


async def test_list_pagination(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    for i in range(5):
        await make_global_exercise(db_session, slug=f"ex-{i}", name=f"Exercise {i}")

    page, total = await exercises.list_exercises(db_session, user_id=user.id, limit=2, offset=0)
    assert total == 5
    assert len(page) == 2


async def test_get_respects_ownership(db_session: AsyncSession) -> None:
    alice = await make_user(db_session, email="alice@example.com")
    bob = await make_user(db_session, email="bob@example.com")
    bob_move = await make_custom_exercise(
        db_session, user_id=bob.id, slug="bob-move", name="Bob Move"
    )

    with pytest.raises(ServiceError) as exc:
        await exercises.get(db_session, user_id=alice.id, exercise_id=bob_move.id)
    assert exc.value.kind.value == "not_found"


async def test_create_custom_derives_slug_and_blocks_duplicates(db_session: AsyncSession) -> None:
    user = await make_user(db_session)

    created = await exercises.create_custom(
        db_session, user_id=user.id, name="My Cool Move", primary_muscles=["core"]
    )
    assert created.slug == "my-cool-move"
    assert created.created_by_user_id == user.id
    assert created.source == "custom"

    with pytest.raises(ServiceError) as exc:
        await exercises.create_custom(db_session, user_id=user.id, name="My Cool Move")
    assert exc.value.kind.value == "conflict"


async def test_create_custom_rejects_empty_slug(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    with pytest.raises(ServiceError) as exc:
        await exercises.create_custom(db_session, user_id=user.id, name="!!!")
    assert exc.value.kind.value == "validation"
