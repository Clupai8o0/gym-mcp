"""POST /api/exercises/{id}/illustration — on-demand generation endpoint (provider stubbed)."""

from __future__ import annotations

import pytest
from app.images import blob, openai_images
from app.images.openai_images import ImageGenerationError
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_global_exercise


async def _fake_generate(*, prompt, size, quality, model, background) -> bytes:  # type: ignore[no-untyped-def]
    return b"PNGDATA"


async def _fake_upload(*, key, data) -> str:  # type: ignore[no-untyped-def]
    return f"https://blob.example/{key}"


async def test_post_illustration_generates_and_persists(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(openai_images, "generate_png", _fake_generate)
    monkeypatch.setattr(blob, "upload_png", _fake_upload)
    exercise = await make_global_exercise(db_session, slug="bench-press", name="Bench Press")

    response = await app_client.post(f"/api/exercises/{exercise.id}/illustration")
    assert response.status_code == 200
    body = response.json()
    assert body["illustration_status"] == "ready"
    assert body["illustration_url"] == "https://blob.example/exercises/bench-press.png"


async def test_post_illustration_unknown_exercise_is_404(
    app_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(openai_images, "generate_png", _fake_generate)
    monkeypatch.setattr(blob, "upload_png", _fake_upload)
    response = await app_client.post(
        "/api/exercises/00000000-0000-0000-0000-000000000000/illustration"
    )
    assert response.status_code == 404
    assert response.json()["error"]["kind"] == "not_found"


async def test_post_illustration_provider_down_is_503(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*, prompt, size, quality, model, background) -> bytes:  # type: ignore[no-untyped-def]
        raise ImageGenerationError("provider down")

    monkeypatch.setattr(openai_images, "generate_png", boom)
    monkeypatch.setattr(blob, "upload_png", _fake_upload)
    exercise = await make_global_exercise(db_session, slug="squat", name="Squat")

    response = await app_client.post(f"/api/exercises/{exercise.id}/illustration")
    assert response.status_code == 503
    assert response.json()["error"]["kind"] == "unavailable"
