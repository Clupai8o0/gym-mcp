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
    # PR rows carry the exercise art for the Dashboard (docs/07 §Dashboard).
    assert items[0]["illustration_status"] == "pending"
    assert items[0]["illustration_url"] is None
    assert items[0]["is_custom"] is False
    assert items[0]["source"] == "auto"

    history = await app_client.get(
        "/api/prs/history", params={"exercise_id": str(exercise.id), "pr_type": "weight"}
    )
    assert history.status_code == 200
    entries = history.json()["items"]
    assert [e["value"] for e in entries] == [100.0, 110.0]
    assert [e["source"] for e in entries] == ["auto", "auto"]


async def test_log_pr_endpoint_records_and_reads_back(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    """``POST /api/prs`` — the REST twin of the MCP ``log_pr`` tool."""
    exercise = await make_global_exercise(db_session, slug="squat", name="Squat")

    created = await app_client.post(
        "/api/prs",
        json={
            "exercise_id": str(exercise.id),
            "pr_type": "weight",
            "value": 140.0,
            "achieved_at": _PERFORMED_AT,
            "notes": "estimated from 5x120",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["value"] == 140.0
    assert body["unit"] == "kg"
    assert body["source"] == "manual"
    assert body["exercise_name"] == "Squat"

    listed = await app_client.get("/api/prs", params={"exercise_id": str(exercise.id)})
    assert [i["source"] for i in listed.json()["items"]] == ["manual"]

    history = await app_client.get(
        "/api/prs/history", params={"exercise_id": str(exercise.id), "pr_type": "weight"}
    )
    assert [e["source"] for e in history.json()["items"]] == ["manual"]


async def test_log_pr_endpoint_rejects_bad_input(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    exercise = await make_global_exercise(db_session, slug="ohp", name="Overhead Press")
    base = {"exercise_id": str(exercise.id), "achieved_at": _PERFORMED_AT}

    negative = await app_client.post("/api/prs", json={**base, "pr_type": "weight", "value": -5})
    assert negative.status_code == 422

    bad_type = await app_client.post("/api/prs", json={**base, "pr_type": "tonnage", "value": 10})
    assert bad_type.status_code == 422
    assert "weight" in bad_type.json()["error"]["message"]

    future = await app_client.post(
        "/api/prs",
        json={
            "exercise_id": str(exercise.id),
            "pr_type": "weight",
            "value": 10,
            "achieved_at": "2099-01-01T00:00:00Z",
        },
    )
    assert future.status_code == 422


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
