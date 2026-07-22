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


# ── get_by_slug: the web Library's detail-page lookup ────────────────────────────────
async def test_get_by_slug_prefers_global_over_custom_collision(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    global_row = await make_global_exercise(db_session, slug="dips", name="Dips")
    await make_custom_exercise(db_session, user_id=user.id, slug="dips", name="My Dips")

    found = await exercises.get_by_slug(db_session, user_id=user.id, slug="dips")
    assert found.id == global_row.id  # global beats a same-slug custom


async def test_get_by_slug_unknown_is_not_found(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    with pytest.raises(ServiceError) as exc:
        await exercises.get_by_slug(db_session, user_id=user.id, slug="nope")
    assert exc.value.kind.value == "not_found"


# ── resolve_ref: the MCP chat-identity rule (docs/04) ────────────────────────────────
async def test_resolve_ref_by_uuid_slug_and_name(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    bench = await make_global_exercise(db_session, slug="bench-press", name="Bench Press")

    by_id = await exercises.resolve_ref(db_session, user_id=user.id, ref=str(bench.id))
    by_slug = await exercises.resolve_ref(db_session, user_id=user.id, ref="bench-press")
    by_name = await exercises.resolve_ref(db_session, user_id=user.id, ref="bench press")
    assert by_id.id == by_slug.id == by_name.id == bench.id


async def test_resolve_ref_unknown_and_empty(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    with pytest.raises(ServiceError) as missing:
        await exercises.resolve_ref(db_session, user_id=user.id, ref="does not exist")
    assert missing.value.kind.value == "not_found"

    with pytest.raises(ServiceError) as empty:
        await exercises.resolve_ref(db_session, user_id=user.id, ref="   ")
    assert empty.value.kind.value == "validation"


async def test_resolve_ref_scopes_visibility(db_session: AsyncSession) -> None:
    alice = await make_user(db_session, email="alice@example.com")
    bob = await make_user(db_session, email="bob@example.com")
    await make_custom_exercise(db_session, user_id=bob.id, slug="bob-move", name="Bob Move")

    with pytest.raises(ServiceError) as exc:  # Bob's custom is invisible to Alice
        await exercises.resolve_ref(db_session, user_id=alice.id, ref="Bob Move")
    assert exc.value.kind.value == "not_found"


async def test_resolve_ref_prefers_global_over_custom_shadow(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    global_bench = await make_global_exercise(db_session, slug="bench-press", name="Bench Press")
    # A custom row sharing the slug (the partial-unique index allows it) must not make it
    # ambiguous — the global wins.
    await make_custom_exercise(db_session, user_id=user.id, slug="bench-press", name="Bench Press")

    resolved = await exercises.resolve_ref(db_session, user_id=user.id, ref="bench-press")
    assert resolved.id == global_bench.id


async def test_resolve_ref_ambiguous_returns_candidates(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    # Two distinct globals sharing a name → a genuine tie at the top tier.
    await make_global_exercise(db_session, slug="pushup-a", name="Push Up")
    await make_global_exercise(db_session, slug="pushup-b", name="Push Up")

    with pytest.raises(ServiceError) as exc:
        await exercises.resolve_ref(db_session, user_id=user.id, ref="Push Up")
    assert exc.value.kind.value == "conflict"
    assert exc.value.details is not None
    assert len(exc.value.details["candidates"]) == 2
