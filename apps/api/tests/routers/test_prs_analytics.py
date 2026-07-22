"""PR + analytics routers, driven through the logging endpoints."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_global_exercise

_PERFORMED_AT = "2026-06-15T18:00:00Z"


async def _log_two_sets(app_client: AsyncClient, exercise_id: str) -> None:
    created = await app_client.post("/api/sessions", json={"performed_at": _PERFORMED_AT})
    session_id = created.json()["id"]
    for n, weight in ((1, 100), (2, 110)):
        await app_client.post(
            f"/api/sessions/{session_id}/sets",
            json={"exercise_id": exercise_id, "set_number": n, "weight_kg": weight, "reps": 5},
        )


async def test_prs_list_and_history(app_client: AsyncClient, db_session: AsyncSession) -> None:
    exercise = await make_global_exercise(db_session, slug="bench", name="Bench")
    await _log_two_sets(app_client, str(exercise.id))

    prs = await app_client.get("/api/prs")
    assert prs.status_code == 200
    items = prs.json()["items"]
    assert len(items) == 1
    assert items[0]["exercise_name"] == "Bench"
    assert items[0]["pr_type"] == "weight"
    assert items[0]["value"] == 110.0

    history = await app_client.get(
        "/api/prs/history", params={"exercise_id": str(exercise.id), "pr_type": "weight"}
    )
    assert history.status_code == 200
    assert [s["weight_kg"] for s in history.json()["items"]] == [100.0, 110.0]


async def test_analytics_volume_and_frequency(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    exercise = await make_global_exercise(db_session, slug="press", name="Press")
    await _log_two_sets(app_client, str(exercise.id))

    volume = await app_client.get(
        "/api/analytics/volume",
        params={"from": "2026-06-01T00:00:00Z", "to": "2026-06-30T00:00:00Z"},
    )
    assert volume.status_code == 200
    vitems = volume.json()["items"]
    assert vitems[0]["exercise_name"] == "Press"
    assert vitems[0]["total_sets"] == 2
    assert vitems[0]["total_tonnage_kg"] == 1050.0  # 100*5 + 110*5

    frequency = await app_client.get("/api/analytics/frequency")
    assert frequency.status_code == 200
    assert frequency.json()["weeks"] == 8
    assert len(frequency.json()["items"]) == 8
