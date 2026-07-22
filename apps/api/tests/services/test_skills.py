"""Skills service: overview defaults, upsert, and validation."""

from __future__ import annotations

import pytest
from app.core.errors import ServiceError
from app.services import skills
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_user


async def test_overview_returns_full_catalog_with_defaults(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    pairs = await skills.overview(db_session, user_id=user.id)

    assert len(pairs) == 13  # the seeded catalog
    assert all(p.progress is None for p in pairs)  # nothing started yet


async def test_upsert_then_reflected_in_overview_and_detail(db_session: AsyncSession) -> None:
    user = await make_user(db_session)

    progress = await skills.upsert_progress(
        db_session,
        user_id=user.id,
        slug="planche",
        current_stage=2,
        progress_percent=40,
        stage_name="tuck planche",
    )
    assert progress.current_stage == 2

    # Upsert again (same skill) — updates in place, no duplicate row.
    await skills.upsert_progress(
        db_session, user_id=user.id, slug="planche", current_stage=3, progress_percent=55
    )
    detail = await skills.detail(db_session, user_id=user.id, slug="planche")
    assert detail.progress is not None
    assert detail.progress.current_stage == 3
    assert detail.progress.progress_percent == 55


async def test_upsert_rejects_stage_beyond_total(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    with pytest.raises(ServiceError) as exc:
        # planche has 6 stages; 99 is out of range.
        await skills.upsert_progress(
            db_session, user_id=user.id, slug="planche", current_stage=99, progress_percent=10
        )
    assert exc.value.kind.value == "validation"


async def test_detail_unknown_skill_is_not_found(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    with pytest.raises(ServiceError) as exc:
        await skills.detail(db_session, user_id=user.id, slug="nonexistent")
    assert exc.value.kind.value == "not_found"
