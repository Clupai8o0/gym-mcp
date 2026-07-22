"""`GET /api/me` returns the stubbed dev user."""

from __future__ import annotations

from httpx import AsyncClient


async def test_me_returns_dev_stub(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/me")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "dev@tempo.local"
    assert body["unit_pref"] == "kg"
