"""Illustration service: single-image routine + on-demand ensure (provider/Blob stubbed)."""

from __future__ import annotations

import uuid

import pytest
from app.core.errors import ServiceError
from app.images.openai_images import ImageGenerationError
from app.models import Exercise
from app.services import images
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_user


async def _fake_generate(
    *, prompt: str, size: str | None, quality: str | None, model: str | None, background: str | None
) -> bytes:
    return b"\x89PNG-fake-bytes"


async def _fake_upload(*, key: str, data: bytes) -> str:
    return f"https://blob.example/{key}"


async def _global_exercise(db: AsyncSession, *, slug: str = "bench-press") -> Exercise:
    exercise = Exercise(
        slug=slug, name="Bench Press", equipment="barbell", primary_muscles=["chest"]
    )
    db.add(exercise)
    await db.flush()
    return exercise


async def test_generate_and_store_marks_ready_with_provenance(db_session: AsyncSession) -> None:
    exercise = await _global_exercise(db_session)
    result = await images.generate_and_store(
        db_session, exercise, trigger="batch", generate=_fake_generate, upload=_fake_upload
    )
    assert result.illustration_status == "ready"
    assert result.illustration_url == "https://blob.example/exercises/bench-press.png"
    meta = result.illustration_meta
    assert meta is not None
    assert meta["trigger"] == "batch"
    assert meta["model"] and meta["prompt_hash"] and meta["style_version"] == "1"
    assert "Bench Press" in meta["prompt"]


async def test_generate_and_store_marks_failed_then_raises(db_session: AsyncSession) -> None:
    exercise = await _global_exercise(db_session)

    async def boom(*, prompt: str, size, quality, model, background) -> bytes:  # type: ignore[no-untyped-def]
        raise ImageGenerationError("upstream 500")

    with pytest.raises(ImageGenerationError):
        await images.generate_and_store(db_session, exercise, generate=boom, upload=_fake_upload)
    assert exercise.illustration_status == "failed"
    assert exercise.illustration_meta is not None
    assert "upstream 500" in exercise.illustration_meta["error"]


async def test_ensure_generates_when_missing(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    exercise = await _global_exercise(db_session)
    result = await images.ensure(
        db_session,
        user_id=user.id,
        exercise_id=exercise.id,
        generate=_fake_generate,
        upload=_fake_upload,
    )
    assert result.illustration_status == "ready"
    assert result.illustration_url is not None
    assert result.illustration_url.endswith("/exercises/bench-press.png")


async def test_ensure_skips_regeneration_when_ready(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    exercise = await _global_exercise(db_session)
    exercise.illustration_status = "ready"
    exercise.illustration_url = "https://blob.example/exercises/bench-press.png"
    await db_session.flush()

    calls: list[int] = []

    async def tracked(*, prompt, size, quality, model, background) -> bytes:  # type: ignore[no-untyped-def]
        calls.append(1)
        return b"x"

    result = await images.ensure(
        db_session, user_id=user.id, exercise_id=exercise.id, generate=tracked, upload=_fake_upload
    )
    assert result.illustration_url == "https://blob.example/exercises/bench-press.png"
    assert calls == []  # no second generation → no double billing


async def test_ensure_reports_in_progress_when_generating(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    exercise = await _global_exercise(db_session)
    exercise.illustration_status = "generating"
    await db_session.flush()

    async def must_not_run(*, prompt, size, quality, model, background) -> bytes:  # type: ignore[no-untyped-def]
        raise AssertionError("should not generate while another run holds 'generating'")

    result = await images.ensure(
        db_session,
        user_id=user.id,
        exercise_id=exercise.id,
        generate=must_not_run,
        upload=_fake_upload,
    )
    assert result.illustration_status == "generating"


async def test_ensure_unknown_exercise_is_not_found(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    with pytest.raises(ServiceError) as excinfo:
        await images.ensure(
            db_session,
            user_id=user.id,
            exercise_id=uuid.uuid4(),
            generate=_fake_generate,
            upload=_fake_upload,
        )
    assert excinfo.value.kind.value == "not_found"


async def test_ensure_maps_provider_failure_to_unavailable(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    exercise = await _global_exercise(db_session)

    async def boom(*, prompt, size, quality, model, background) -> bytes:  # type: ignore[no-untyped-def]
        raise ImageGenerationError("provider down")

    with pytest.raises(ServiceError) as excinfo:
        await images.ensure(
            db_session, user_id=user.id, exercise_id=exercise.id, generate=boom, upload=_fake_upload
        )
    assert excinfo.value.kind.value == "unavailable"
