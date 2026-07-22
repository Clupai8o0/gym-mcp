"""Error envelope + request-id header contract (docs/12)."""

from __future__ import annotations

from httpx import AsyncClient


async def test_not_found_envelope(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/exercises/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["kind"] == "not_found"
    assert isinstance(error["message"], str)


async def test_validation_envelope_carries_details(app_client: AsyncClient) -> None:
    response = await app_client.post("/api/exercises", json={})  # missing required 'name'
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["kind"] == "validation"
    assert isinstance(error["details"], list)


async def test_request_id_header_present(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/health")
    assert response.headers.get("X-Request-ID")


async def test_supplied_request_id_is_echoed(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/health", headers={"X-Request-ID": "abc123"})
    assert response.headers.get("X-Request-ID") == "abc123"
