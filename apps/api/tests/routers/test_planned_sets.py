"""Planning over REST: write a prescription → work through it → finish and read adherence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_global_exercise


async def _seed_exercise(db_session: AsyncSession) -> str:
    exercise = await make_global_exercise(db_session, slug="bench-press", name="Bench Press")
    return str(exercise.id)


async def test_plan_then_work_through_it(app_client: AsyncClient, db_session: AsyncSession) -> None:
    exercise_id = await _seed_exercise(db_session)
    now = datetime.now(tz=UTC).isoformat()

    planned = await app_client.post(
        "/api/sessions/planned",
        json={
            "performed_at": now,
            "title": "Upper — Power",
            "type": "upper",
            "planned_sets": [
                {
                    "exercise_id": exercise_id,
                    "set_number": n,
                    "target_reps_min": 5,
                    "target_reps_max": 5,
                    "target_weight_kg": 100,
                }
                for n in (1, 2, 3)
            ],
        },
    )
    assert planned.status_code == 201
    body = planned.json()
    session_id = body["session_id"]
    assert body["planned_total"] == 3 and body["completed_count"] == 0
    assert [item["planned"]["order_index"] for item in body["items"]] == [0, 1, 2]
    assert all(item["is_completed"] is False for item in body["items"])
    assert body["items"][0]["exercise"]["name"] == "Bench Press"

    # The session exists with a plan and no sets, and `/active` says so.
    active = (await app_client.get("/api/sessions/active")).json()
    assert active["session"]["id"] == session_id
    assert active["set_count"] == 0
    assert active["planned_total"] == 3 and active["completed_count"] == 0

    # Nothing prescribed counts as training yet.
    frm = (datetime.now(tz=UTC) - timedelta(days=1)).isoformat()
    to = (datetime.now(tz=UTC) + timedelta(days=1)).isoformat()
    volume = await app_client.get("/api/analytics/volume", params={"from": frm, "to": to})
    assert volume.json()["items"] == []

    # Do the first two sets.
    first_line = body["items"][0]["planned"]["id"]
    done = await app_client.post(
        f"/api/planned-sets/{first_line}/complete", json={"weight_kg": 100, "reps": 5}
    )
    assert done.status_code == 201
    assert done.json()["logged"]["pr"]["pr_type"] == "weight"
    assert done.json()["planned"]["completed_set_id"] == done.json()["logged"]["set"]["id"]

    second_line = body["items"][1]["planned"]["id"]
    assert (
        await app_client.post(
            f"/api/planned-sets/{second_line}/complete", json={"weight_kg": 102.5, "reps": 5}
        )
    ).status_code == 201

    progress = (await app_client.get(f"/api/sessions/{session_id}/progress")).json()
    assert progress["adherence"] == {
        "planned_total": 3,
        "completed_count": 2,
        "pending_count": 1,
        "off_plan_count": 0,
        "percent": 66.7,
    }
    assert progress["next_up"]["planned"]["id"] == body["items"][2]["planned"]["id"]
    assert progress["remaining_exercises"][0]["remaining"] == 1

    finished = await app_client.post(f"/api/sessions/{session_id}/finish")
    assert finished.status_code == 200
    assert finished.json()["duration_minutes"] is not None
    assert finished.json()["adherence"]["completed_count"] == 2
    assert finished.json()["adherence"]["percent"] == 66.7


async def test_off_plan_sets_are_logged_and_reported(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Training that nobody wrote down is never refused — only counted separately."""
    exercise_id = await _seed_exercise(db_session)
    now = datetime.now(tz=UTC).isoformat()
    planned = await app_client.post(
        "/api/sessions/planned",
        json={
            "performed_at": now,
            "planned_sets": [{"exercise_id": exercise_id, "set_number": 1}],
        },
    )
    session_id = planned.json()["session_id"]

    logged = await app_client.post(
        f"/api/sessions/{session_id}/sets",
        json={"exercise_id": exercise_id, "set_number": 9, "weight_kg": 60, "reps": 12},
    )
    assert logged.status_code == 201

    progress = (await app_client.get(f"/api/sessions/{session_id}/progress")).json()
    assert progress["adherence"]["off_plan_count"] == 1
    assert progress["adherence"]["completed_count"] == 0
    assert progress["logged_total"] == 1


async def test_correcting_and_removing_a_line(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    exercise_id = await _seed_exercise(db_session)
    now = datetime.now(tz=UTC).isoformat()
    planned = await app_client.post(
        "/api/sessions/planned",
        json={
            "performed_at": now,
            "planned_sets": [
                {"exercise_id": exercise_id, "set_number": 1, "target_weight_kg": 100}
            ],
        },
    )
    session_id = planned.json()["session_id"]
    line_id = planned.json()["items"][0]["planned"]["id"]

    patched = await app_client.patch(
        f"/api/planned-sets/{line_id}", json={"target_weight_kg": 105, "target_reps_min": 3}
    )
    assert patched.status_code == 200
    assert patched.json()["target_weight_kg"] == 105.0
    assert patched.json()["target_reps_min"] == 3

    removed = await app_client.delete(f"/api/planned-sets/{line_id}")
    assert removed.status_code == 200 and removed.json()["id"] == line_id
    assert (await app_client.get(f"/api/sessions/{session_id}/planned")).json()["items"] == []

    # Soft, so the correction tooling undoes it.
    restored = await app_client.post(
        "/api/corrections/restore", json={"entity_type": "planned_set", "entity_id": line_id}
    )
    assert restored.status_code == 200
    assert len((await app_client.get(f"/api/sessions/{session_id}/planned")).json()["items"]) == 1


async def test_completing_the_same_line_twice_is_a_409(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    exercise_id = await _seed_exercise(db_session)
    planned = await app_client.post(
        "/api/sessions/planned",
        json={
            "performed_at": datetime.now(tz=UTC).isoformat(),
            "planned_sets": [{"exercise_id": exercise_id, "set_number": 1}],
        },
    )
    line_id = planned.json()["items"][0]["planned"]["id"]

    assert (
        await app_client.post(f"/api/planned-sets/{line_id}/complete", json={"reps": 10})
    ).status_code == 201
    conflict = await app_client.post(f"/api/planned-sets/{line_id}/complete", json={"reps": 8})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["kind"] == "conflict"


async def test_planning_a_missing_session_is_404(app_client: AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await app_client.get(f"/api/sessions/{missing}/planned")).status_code == 404
    assert (await app_client.get(f"/api/sessions/{missing}/progress")).status_code == 404
    assert (
        await app_client.patch(f"/api/planned-sets/{missing}", json={"reps": 1})
    ).status_code in (
        404,
        422,
    )
