"""`GET /api/me` returns the stubbed dev user; `PATCH /api/me` updates preferences."""

from __future__ import annotations

from httpx import AsyncClient


async def test_me_returns_dev_stub(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/me")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "dev@tempo.local"
    assert body["unit_pref"] == "kg"


async def test_patch_me_updates_unit_pref(app_client: AsyncClient) -> None:
    patched = await app_client.patch("/api/me", json={"unit_pref": "lb"})
    assert patched.status_code == 200
    assert patched.json()["unit_pref"] == "lb"

    # The change persists on the next read.
    assert (await app_client.get("/api/me")).json()["unit_pref"] == "lb"


async def test_patch_me_rejects_bad_unit(app_client: AsyncClient) -> None:
    response = await app_client.patch("/api/me", json={"unit_pref": "stone"})
    assert response.status_code == 422
