"""Exercise router: list/filter, create custom, detail, and error mapping."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_global_exercise


async def test_list_includes_global_and_reports_total(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    await make_global_exercise(db_session, slug="bench-press", name="Bench Press")

    response = await app_client.get("/api/exercises")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 50 and body["offset"] == 0
    assert body["items"][0]["name"] == "Bench Press"
    assert body["items"][0]["is_custom"] is False
    assert "created_by_user_id" not in body["items"][0]  # internal id not leaked


async def test_create_custom_and_fetch_detail(app_client: AsyncClient) -> None:
    create = await app_client.post(
        "/api/exercises",
        json={"name": "My Cool Move", "instructions": ["Step one", "Step two"]},
    )
    assert create.status_code == 201
    created = create.json()
    assert created["slug"] == "my-cool-move"
    assert created["is_custom"] is True
    assert created["instructions"] == ["Step one", "Step two"]

    detail = await app_client.get(f"/api/exercises/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["instructions"] == ["Step one", "Step two"]


async def test_get_by_slug_returns_detail(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    await make_global_exercise(db_session, slug="barbell-bench-press", name="Barbell Bench Press")

    response = await app_client.get("/api/exercises/by-slug/barbell-bench-press")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Barbell Bench Press"
    assert body["slug"] == "barbell-bench-press"
    assert "instructions" in body  # detail shape, not summary


async def test_get_by_unknown_slug_is_404(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/exercises/by-slug/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["kind"] == "not_found"


async def test_duplicate_custom_slug_conflicts(app_client: AsyncClient) -> None:
    await app_client.post("/api/exercises", json={"name": "Dup Move"})
    second = await app_client.post("/api/exercises", json={"name": "Dup Move"})
    assert second.status_code == 409
    assert second.json()["error"]["kind"] == "conflict"


async def test_get_unknown_exercise_is_404(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/exercises/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["kind"] == "not_found"


async def test_filter_by_query(app_client: AsyncClient, db_session: AsyncSession) -> None:
    await make_global_exercise(db_session, slug="back-squat", name="Back Squat")
    await make_global_exercise(db_session, slug="bench", name="Bench")

    response = await app_client.get("/api/exercises", params={"q": "squat"})
    names = [e["name"] for e in response.json()["items"]]
    assert names == ["Back Squat"]
