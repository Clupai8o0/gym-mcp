"""Health probe now pings the DB (docs/03 backend-skeleton DoD)."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_ok(app_client: AsyncClient) -> None:
    response = await app_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}
