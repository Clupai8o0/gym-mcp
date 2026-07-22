"""Catalog import service: insert/update/skip counting, idempotency, art + custom preservation."""

from __future__ import annotations

from app.catalog.dataset import SOURCE, CatalogRecord
from app.core.slugs import slugify
from app.models import Exercise
from app.services import catalog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_custom_exercise, make_user


def _record(source_id: str, name: str, **overrides: object) -> CatalogRecord:
    data: dict[str, object] = {
        "source": SOURCE,
        "source_id": source_id,
        "slug": slugify(name),
        "name": name,
        "category": "strength",
        "force": None,
        "level": "beginner",
        "mechanic": None,
        "equipment": "barbell",
        "primary_muscles": ["chest"],
        "secondary_muscles": [],
        "instructions": ["Step one."],
    }
    data.update(overrides)
    return CatalogRecord(**data)


async def _get(db: AsyncSession, source_id: str) -> Exercise:
    return (await db.execute(select(Exercise).where(Exercise.source_id == source_id))).scalar_one()


async def test_inserts_new_rows(db_session: AsyncSession) -> None:
    summary = await catalog.upsert_exercises(
        db_session, [_record("A", "Alpha Lift"), _record("B", "Beta Lift")]
    )
    assert (summary.inserted, summary.updated, summary.skipped) == (2, 0, 0)
    assert summary.total == 2
    row = await _get(db_session, "A")
    assert row.slug == "alpha-lift"
    assert row.created_by_user_id is None  # global catalog row
    assert row.illustration_status == "pending"


async def test_reimport_is_idempotent(db_session: AsyncSession) -> None:
    records = [_record("A", "Alpha Lift"), _record("B", "Beta Lift")]
    await catalog.upsert_exercises(db_session, records)
    summary = await catalog.upsert_exercises(db_session, records)
    assert (summary.inserted, summary.updated, summary.skipped) == (0, 0, 2)


async def test_changed_metadata_updates_and_bumps_updated_at(db_session: AsyncSession) -> None:
    await catalog.upsert_exercises(db_session, [_record("A", "Alpha", category="strength")])
    before = await _get(db_session, "A")
    original_updated_at = before.updated_at

    summary = await catalog.upsert_exercises(
        db_session, [_record("A", "Alpha", category="cardio", primary_muscles=["quadriceps"])]
    )
    assert (summary.inserted, summary.updated, summary.skipped) == (0, 1, 0)
    after = await _get(db_session, "A")
    assert after.category == "cardio"
    assert after.primary_muscles == ["quadriceps"]
    assert after.updated_at >= original_updated_at


async def test_reimport_preserves_generated_art(db_session: AsyncSession) -> None:
    await catalog.upsert_exercises(db_session, [_record("A", "Alpha", category="strength")])
    row = await _get(db_session, "A")
    row.illustration_url = "https://blob.example/exercises/alpha.png"
    row.illustration_status = "ready"
    row.illustration_meta = {"model": "gpt-image-2"}
    await db_session.flush()

    # A metadata change must not clobber the image.
    await catalog.upsert_exercises(db_session, [_record("A", "Alpha", category="cardio")])
    refreshed = await _get(db_session, "A")
    assert refreshed.category == "cardio"
    assert refreshed.illustration_status == "ready"
    assert refreshed.illustration_url == "https://blob.example/exercises/alpha.png"
    assert refreshed.illustration_meta == {"model": "gpt-image-2"}


async def test_ignores_custom_rows(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    custom = await make_custom_exercise(db_session, user_id=user.id, slug="alpha", name="Alpha")
    # A global row with the same slug coexists (partial unique indexes) and is inserted fresh;
    # the user's custom row is never read or mutated by the importer.
    summary = await catalog.upsert_exercises(db_session, [_record("A", "Alpha")])
    assert summary.inserted == 1
    await db_session.refresh(custom)
    assert custom.source == "custom"
    assert custom.created_by_user_id == user.id


async def test_empty_import_is_a_noop(db_session: AsyncSession) -> None:
    summary = await catalog.upsert_exercises(db_session, [])
    assert (summary.inserted, summary.updated, summary.skipped) == (0, 0, 0)
