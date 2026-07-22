"""Skills router: overview, upsert progress, detail, and validation."""

from __future__ import annotations

from httpx import AsyncClient


async def test_overview_lists_full_catalog(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/skills")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 13
    assert all(item["current_stage"] == 0 for item in items)


async def test_upsert_then_detail(app_client: AsyncClient) -> None:
    put = await app_client.put(
        "/api/skills/planche/progress",
        json={"current_stage": 2, "progress_percent": 40, "stage_name": "tuck"},
    )
    assert put.status_code == 200
    assert put.json()["current_stage"] == 2

    detail = await app_client.get("/api/skills/planche")
    assert detail.status_code == 200
    assert detail.json()["progress"]["progress_percent"] == 40


async def test_unknown_skill_is_404(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/skills/nope")
    assert response.status_code == 404
    assert response.json()["error"]["kind"] == "not_found"


async def test_progress_percent_out_of_range_is_422(app_client: AsyncClient) -> None:
    response = await app_client.put(
        "/api/skills/planche/progress", json={"current_stage": 1, "progress_percent": 150}
    )
    assert response.status_code == 422
