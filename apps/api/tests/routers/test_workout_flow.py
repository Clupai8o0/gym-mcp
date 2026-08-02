"""End-to-end workout loop over REST: create session → log sets (PRs) → detail → edit → delete."""

from __future__ import annotations

from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_global_exercise

_PERFORMED_AT = "2026-06-15T18:00:00Z"


async def _seed_exercise(db_session: AsyncSession) -> str:
    exercise = await make_global_exercise(db_session, slug="bench-press", name="Bench Press")
    return str(exercise.id)


async def test_full_session_and_set_lifecycle(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    exercise_id = await _seed_exercise(db_session)

    # Create a session.
    created = await app_client.post(
        "/api/sessions", json={"performed_at": _PERFORMED_AT, "title": "Upper", "type": "push"}
    )
    assert created.status_code == 201
    session_id = created.json()["id"]

    # Log two sets — the second is a weight PR over the first.
    first = await app_client.post(
        f"/api/sessions/{session_id}/sets",
        json={"exercise_id": exercise_id, "set_number": 1, "weight_kg": 100, "reps": 5},
    )
    assert first.status_code == 201
    assert first.json()["pr"]["pr_type"] == "weight"

    second = await app_client.post(
        f"/api/sessions/{session_id}/sets",
        json={"exercise_id": exercise_id, "set_number": 2, "weight_kg": 110, "reps": 5},
    )
    body = second.json()
    assert body["pr"]["is_pr"] is True
    assert body["pr"]["previous_best"] == 100.0
    assert body["pr"]["new_value"] == 110.0
    second_set_id = body["set"]["id"]

    # Session detail groups sets under the exercise.
    detail = await app_client.get(f"/api/sessions/{session_id}")
    assert detail.status_code == 200
    groups = detail.json()["exercises"]
    assert len(groups) == 1
    assert groups[0]["exercise"]["name"] == "Bench Press"
    assert len(groups[0]["sets"]) == 2

    # Edit the top set down; PR recomputes.
    patched = await app_client.patch(f"/api/sets/{second_set_id}", json={"weight_kg": 90})
    assert patched.status_code == 200

    # Delete it.
    deleted = await app_client.delete(f"/api/sets/{second_set_id}")
    assert deleted.status_code == 204

    # Update + delete the session.
    upd = await app_client.patch(f"/api/sessions/{session_id}", json={"title": "Upper — Power"})
    assert upd.status_code == 200 and upd.json()["title"] == "Upper — Power"

    gone = await app_client.delete(f"/api/sessions/{session_id}")
    assert gone.status_code == 204
    assert (await app_client.get(f"/api/sessions/{session_id}")).status_code == 404


async def test_list_sessions_paginates(app_client: AsyncClient) -> None:
    for i in range(3):
        await app_client.post(
            "/api/sessions", json={"performed_at": _PERFORMED_AT, "title": f"S{i}"}
        )

    response = await app_client.get("/api/sessions", params={"limit": 2})
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


async def test_log_set_into_missing_session_is_404(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    exercise_id = await _seed_exercise(db_session)
    response = await app_client.post(
        "/api/sessions/00000000-0000-0000-0000-000000000000/sets",
        json={"exercise_id": exercise_id, "set_number": 1, "reps": 5},
    )
    assert response.status_code == 404


async def test_active_and_finish_endpoints(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`GET /active` reflects the lifecycle, and `/finish` is idempotent over HTTP (Phase 11A)."""
    idle = (await app_client.get("/api/sessions/active")).json()
    assert idle["session"] is None and idle["set_count"] == 0

    # Started *now* — a backfilled historical session (like `_PERFORMED_AT`) is deliberately
    # never "active": it is already older than the staleness window.
    now = datetime.now(tz=UTC).isoformat()
    created = await app_client.post("/api/sessions", json={"performed_at": now})
    session_id = created.json()["id"]
    assert created.json()["ended_at"] is None

    active = await app_client.get("/api/sessions/active")
    assert active.status_code == 200
    assert active.json()["session"]["id"] == session_id
    # The count rides along, so the session bar never fetches the whole detail to say "N sets".
    assert active.json()["set_count"] == 0

    finished = await app_client.post(f"/api/sessions/{session_id}/finish")
    assert finished.status_code == 200
    body = finished.json()
    assert body["ended_at"] is not None and body["duration_minutes"] is not None

    again = await app_client.post(f"/api/sessions/{session_id}/finish")
    assert again.status_code == 200 and again.json()["ended_at"] == body["ended_at"]

    assert (await app_client.get("/api/sessions/active")).json()["session"] is None


async def test_finish_missing_session_is_404(app_client: AsyncClient) -> None:
    response = await app_client.post("/api/sessions/00000000-0000-0000-0000-000000000000/finish")
    assert response.status_code == 404


async def test_log_set_without_measurement_is_422(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    exercise_id = await _seed_exercise(db_session)
    created = await app_client.post("/api/sessions", json={"performed_at": _PERFORMED_AT})
    session_id = created.json()["id"]

    response = await app_client.post(
        f"/api/sessions/{session_id}/sets",
        json={"exercise_id": exercise_id, "set_number": 1, "rpe": 8},
    )
    assert response.status_code == 422
    assert response.json()["error"]["kind"] == "validation"
