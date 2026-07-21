"""Smoke test for the liveness probe (Phase 0 acceptance)."""

from __future__ import annotations

from app.main import app
from fastapi.testclient import TestClient


def test_health_ok() -> None:
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
