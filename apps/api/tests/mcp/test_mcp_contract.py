"""MCP ↔ REST contract tests: no drift between the two surfaces (docs/03, docs/04, docs/12).

Every MCP tool calls the same service and returns the same Pydantic schema as its REST sibling,
so for identical inputs the two must return **identical data**. Each read tool is compared byte
-for-byte against its REST endpoint; each write tool's result is checked to round-trip through
REST. Both surfaces run against the same rolled-back session as the same user, so any divergence
is a real contract break, not test noise.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.core.errors import ErrorKind, ServiceError
from app.mcp import server
from app.services import sessions as sessions_service
from app.services import sets as sets_service
from app.services import skills as skills_service
from app.services import users as users_service
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._factories import make_custom_exercise, make_global_exercise
from tests.mcp._mcphelp import bound

# The shared session models a workout **in progress**, so it has to have started recently:
# `sessions.create` now closes anything older than `STALE_AFTER` at creation, and
# `get_active_session` will not return a session that started longer ago than a workout lasts.
_NOW = datetime.now(tz=UTC)
_PERFORMED_AT = _NOW - timedelta(minutes=30)


@pytest.fixture
async def seeded(db_session: AsyncSession) -> dict[str, Any]:
    """Provision the REST dev user and a realistic slice of their data (one shared session)."""
    user = await users_service.ensure_dev_user(db_session)
    bench = await make_global_exercise(db_session, slug="bench-press", name="Bench Press")
    await make_custom_exercise(db_session, user_id=user.id, slug="my-move", name="My Move")

    session = await sessions_service.create(
        db_session, user_id=user.id, performed_at=_PERFORMED_AT, type="upper", title="Push day"
    )
    await sets_service.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=bench.id,
        set_number=1,
        weight_kg=80,
        reps=5,
    )
    await sets_service.log_set(
        db_session,
        user_id=user.id,
        session_id=session.id,
        exercise_id=bench.id,
        set_number=2,
        weight_kg=85,
        reps=5,
    )
    overview = await skills_service.overview(db_session, user_id=user.id)
    skill_slug = overview[0].skill.slug
    return {
        "user_id": user.id,
        "bench_id": bench.id,
        "session_id": session.id,
        "skill_slug": skill_slug,
    }


async def _rest(client: AsyncClient, path: str, **params: Any) -> Any:
    response = await client.get(path, params=params or None)
    assert response.status_code == 200, response.text
    return response.json()


# ── Read parity: MCP tool output == REST endpoint output ─────────────────────────────
async def test_search_exercises_matches_rest(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    rest = await _rest(app_client, "/api/exercises", q="bench")
    with bound(db_session, seeded["user_id"]):
        mcp = await server.search_exercises(query="bench")
    assert mcp == rest


async def test_get_exercise_matches_rest(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    rest = await _rest(app_client, f"/api/exercises/{seeded['bench_id']}")
    with bound(db_session, seeded["user_id"]):
        by_id = await server.get_exercise(exercise=str(seeded["bench_id"]))
        by_slug = await server.get_exercise(exercise="bench-press")
        by_name = await server.get_exercise(exercise="Bench Press")
    assert by_id == rest  # the chat-identity rule resolves UUID, slug, and name alike
    assert by_slug == rest
    assert by_name == rest


async def test_list_sessions_matches_rest(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    rest = await _rest(app_client, "/api/sessions")
    with bound(db_session, seeded["user_id"]):
        mcp = await server.list_sessions()
    assert mcp == rest


async def test_get_session_matches_rest(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    rest = await _rest(app_client, f"/api/sessions/{seeded['session_id']}")
    with bound(db_session, seeded["user_id"]):
        mcp = await server.get_session(session_id=seeded["session_id"])
    assert mcp == rest


async def test_get_active_session_matches_rest(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    rest = await _rest(app_client, "/api/sessions/active")
    with bound(db_session, seeded["user_id"]):
        mcp = await server.get_active_session()
    assert mcp == rest
    assert mcp["session"]["id"] == str(seeded["session_id"])
    assert mcp["set_count"] == 2  # the fixture's two bench sets, counted without a detail fetch


async def test_get_prs_matches_rest(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    rest = await _rest(app_client, "/api/prs")
    with bound(db_session, seeded["user_id"]):
        mcp = await server.get_prs()
    assert mcp == rest


async def test_get_pr_history_matches_rest(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    rest = await _rest(
        app_client, "/api/prs/history", exercise_id=str(seeded["bench_id"]), pr_type="weight"
    )
    with bound(db_session, seeded["user_id"]):
        mcp = await server.get_pr_history(exercise="bench-press", pr_type="weight")
    assert mcp == rest


async def test_volume_matches_rest(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    frm = (_NOW - timedelta(days=30)).isoformat()
    to = (_NOW + timedelta(days=1)).isoformat()
    rest = await _rest(app_client, "/api/analytics/volume", **{"from": frm, "to": to})
    with bound(db_session, seeded["user_id"]):
        mcp = await server.get_volume_summary(
            date_from=datetime.fromisoformat(frm), date_to=datetime.fromisoformat(to)
        )
    assert mcp == rest


async def test_frequency_matches_rest(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    rest = await _rest(app_client, "/api/analytics/frequency", weeks=6)
    with bound(db_session, seeded["user_id"]):
        mcp = await server.get_session_frequency(weeks=6)
    assert mcp == rest


async def test_skill_overview_and_detail_match_rest(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    slug = seeded["skill_slug"]
    rest_overview = await _rest(app_client, "/api/skills")
    rest_detail = await _rest(app_client, f"/api/skills/{slug}")
    with bound(db_session, seeded["user_id"]):
        mcp_overview = await server.get_skill_overview()
        mcp_detail = await server.get_skill_detail(slug=slug)
    assert mcp_overview == rest_overview
    assert mcp_detail == rest_detail


# ── Write parity: an MCP write round-trips through REST identically ───────────────────
async def test_log_session_then_rest_reads_it(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    with bound(db_session, seeded["user_id"]):
        created = await server.log_session(
            performed_at=_NOW - timedelta(days=2), type="lower", title="Legs"
        )
    rest = await _rest(app_client, f"/api/sessions/{created['id']}")
    assert {k: rest[k] for k in created} == created  # every field the MCP write returned matches


async def test_finish_session_then_rest_reads_it(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    with bound(db_session, seeded["user_id"]):
        finished = await server.finish_session(session_id=seeded["session_id"])
    assert finished["ended_at"] is not None and finished["duration_minutes"] is not None
    # Finishing reports adherence. This session was logged without a plan, so there is nothing to
    # adhere to — `percent` is null rather than 0 or 100, either of which would be a claim about a
    # prescription that never existed.
    assert finished["adherence"] == {
        "planned_total": 0,
        "completed_count": 0,
        "pending_count": 0,
        "off_plan_count": 2,
        "percent": None,
    }

    rest = await _rest(app_client, f"/api/sessions/{seeded['session_id']}")
    # Projected onto the *session* fields: `adherence` is computed for the finish response and has
    # no counterpart on the session detail, so comparing it against `rest` would be asking the
    # wrong endpoint a question it was never meant to answer.
    session_fields = {k: v for k, v in finished.items() if k != "adherence"}
    assert {k: rest[k] for k in session_fields} == session_fields
    # …and the REST view of "active" agrees the workout is over.
    assert (await _rest(app_client, "/api/sessions/active"))["session"] is None


async def test_create_custom_exercise_then_rest_reads_it(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    with bound(db_session, seeded["user_id"]):
        created = await server.create_custom_exercise(name="Ring Dip", primary_muscles=["chest"])
    assert created["is_custom"] is True
    rest = await _rest(app_client, f"/api/exercises/{created['id']}")
    assert rest == created


async def test_log_set_shape_matches_rest_sibling(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    # Same service both ways; assert the MCP result carries REST's LoggedSetOut shape + PR verdict.
    with bound(db_session, seeded["user_id"]):
        logged = await server.log_set(
            session_id=seeded["session_id"],
            exercise="bench-press",
            set_number=3,
            weight_kg=90,
            reps=3,
        )
    assert set(logged) == {"set", "pr"}
    assert set(logged["set"]) == {
        "id",
        "session_id",
        "exercise_id",
        "set_number",
        "weight_kg",
        "reps",
        "hold_seconds",
        "rpe",
        "is_pr",
        "pr_type",
        "notes",
        "is_backfill",
        "created_at",
    }
    assert logged["pr"]["is_pr"] is True and logged["pr"]["pr_type"] == "weight"


async def test_log_pr_then_rest_reads_it(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    """``log_pr`` writes a manual record the REST surface sees identically."""
    with bound(db_session, seeded["user_id"]):
        # Dated *after* the session, which is the realistic shape: you train, then enter the
        # estimate. A claim dated *during* the session would outrank its sets at their own
        # moment, and those sets would correctly stop being records.
        created = await server.log_pr(
            exercise="bench-press",
            pr_type="weight",
            value=120.0,
            achieved_at=_NOW,
            notes="estimated 1RM",
        )
    assert created["source"] == "manual"
    assert created["value"] == 120.0 and created["unit"] == "kg"

    rest = await _rest(app_client, "/api/prs", exercise_id=str(seeded["bench_id"]))
    weight = next(i for i in rest["items"] if i["pr_type"] == "weight")
    assert weight == created

    # And it shows up in the chronology alongside the auto entries from the seeded sets.
    history = await _rest(
        app_client, "/api/prs/history", exercise_id=str(seeded["bench_id"]), pr_type="weight"
    )
    assert [i["source"] for i in history["items"]] == ["auto", "auto", "manual"]


async def test_log_pr_unknown_exercise_is_a_clean_error(
    db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    """An unresolvable name must surface as a domain error, never a 500."""
    with bound(db_session, seeded["user_id"]), pytest.raises(ServiceError) as caught:
        await server.log_pr(
            exercise="kettlebell moonwalk",
            pr_type="weight",
            value=100.0,
            achieved_at=_PERFORMED_AT,
        )
    assert caught.value.kind is ErrorKind.NOT_FOUND
    assert caught.value.status_code == 404


# ── Planning parity: the prescription reads and writes identically on both surfaces ──
async def test_plan_session_then_rest_reads_the_same_prescription(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    with bound(db_session, seeded["user_id"]):
        plan = await server.plan_session(
            performed_at=_NOW + timedelta(days=2),
            title="Tuesday — Upper",
            type="upper",
            planned_sets=[
                {
                    "exercise": "bench-press",  # the chat-identity rule applies here too
                    "set_number": n,
                    "target_reps_min": 5,
                    "target_reps_max": 5,
                    "target_weight_kg": 100,
                }
                for n in (1, 2, 3)
            ],
        )
    assert plan["planned_total"] == 3 and plan["completed_count"] == 0

    rest = await _rest(app_client, f"/api/sessions/{plan['session_id']}/planned")
    assert rest == plan


async def test_session_progress_matches_rest(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    """The seeded session has two logged sets and no plan — the honest answer is 'nothing to
    adhere to', not 0% or 100%."""
    rest = await _rest(app_client, f"/api/sessions/{seeded['session_id']}/progress")
    with bound(db_session, seeded["user_id"]):
        mcp = await server.session_progress(session_id=seeded["session_id"])
    assert mcp == rest
    assert mcp["adherence"]["percent"] is None
    assert mcp["adherence"]["off_plan_count"] == 2
    assert mcp["next_up"] is None


async def test_complete_planned_set_writes_a_real_set_rest_can_see(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    """The one door between the plan and the data: it goes through `sets.log_set`, PRs and all."""
    with bound(db_session, seeded["user_id"]):
        plan = await server.add_planned_sets(
            session_id=seeded["session_id"],
            planned_sets=[{"exercise": "bench-press", "set_number": 3, "target_reps_min": 3}],
        )
        line_id = plan["items"][0]["planned"]["id"]
        done = await server.complete_planned_set(
            planned_set_id=uuid.UUID(line_id), weight_kg=95, reps=3
        )

    assert set(done) == {"planned", "logged"}
    assert done["logged"]["pr"]["is_pr"] is True  # 95 kg beats the seeded 85 kg
    assert done["planned"]["completed_set_id"] == done["logged"]["set"]["id"]

    # REST sees the same set inside the session, and the same completion state on the plan.
    detail = await _rest(app_client, f"/api/sessions/{seeded['session_id']}")
    logged_ids = {row["id"] for group in detail["exercises"] for row in group["sets"]}
    assert done["logged"]["set"]["id"] in logged_ids

    rest_plan = await _rest(app_client, f"/api/sessions/{seeded['session_id']}/planned")
    assert rest_plan["completed_count"] == 1
    assert rest_plan["items"][0]["is_completed"] is True


async def test_a_prescription_does_not_move_volume_or_records(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    """The invariant, asserted across the surface a chat client actually uses."""
    frm = (_NOW - timedelta(days=30)).isoformat()
    to = (_NOW + timedelta(days=1)).isoformat()
    before_volume = await _rest(app_client, "/api/analytics/volume", **{"from": frm, "to": to})
    before_prs = await _rest(app_client, "/api/prs")

    with bound(db_session, seeded["user_id"]):
        await server.add_planned_sets(
            session_id=seeded["session_id"],
            planned_sets=[
                {"exercise": "bench-press", "set_number": n, "target_weight_kg": 300}
                for n in (3, 4, 5)
            ],
        )

    assert await _rest(app_client, "/api/analytics/volume", **{"from": frm, "to": to}) == (
        before_volume
    )
    assert await _rest(app_client, "/api/prs") == before_prs


async def test_active_session_reports_the_plan_on_both_surfaces(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    with bound(db_session, seeded["user_id"]):
        await server.add_planned_sets(
            session_id=seeded["session_id"],
            planned_sets=[{"exercise": "bench-press", "set_number": 3}],
        )
        mcp = await server.get_active_session()
    rest = await _rest(app_client, "/api/sessions/active")
    assert mcp == rest
    assert mcp["planned_total"] == 1 and mcp["completed_count"] == 0
    assert mcp["set_count"] == 2, "logged sets and prescribed lines are different questions"


async def test_update_skill_progress_then_rest_reads_it(
    app_client: AsyncClient, db_session: AsyncSession, seeded: dict[str, Any]
) -> None:
    slug = seeded["skill_slug"]
    with bound(db_session, seeded["user_id"]):
        updated = await server.update_skill_progress(
            slug=slug, current_stage=1, progress_percent=40
        )
    assert updated["current_stage"] == 1 and updated["progress_percent"] == 40
    rest_detail = await _rest(app_client, f"/api/skills/{slug}")
    assert rest_detail["progress"]["current_stage"] == 1
    assert rest_detail["progress"]["progress_percent"] == 40
