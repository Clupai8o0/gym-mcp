"""The ``/mcp`` Streamable-HTTP endpoint over the wire: OAuth guard + real tool calls.

Proves the mount works end-to-end (docs/04): unauthenticated/invalid/insufficient-scope
requests are rejected with the RFC 9728 pointer, and a valid bearer can list tools, read the
guide resource, and drive the full log-a-workout loop with PR detection — the same services
REST calls, reached through the MCP protocol.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._authhelp import mint_access_token
from tests._factories import make_global_exercise, make_user
from tests.mcp._mcphelp import rpc, tool_error_text, tool_result


async def test_unauthenticated_401_with_prm_pointer(mcp_http: AsyncClient) -> None:
    response = await rpc(mcp_http, "tools/list")
    assert response.status_code == 401
    www = response.headers["www-authenticate"]
    assert www.startswith("Bearer ")
    assert "/.well-known/oauth-protected-resource" in www


async def test_invalid_token_401(mcp_http: AsyncClient) -> None:
    response = await rpc(mcp_http, "tools/list", token="not-a-real-token")
    assert response.status_code == 401


async def test_insufficient_scope_403(mcp_http: AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    _client, tokens = await mint_access_token(db_session, user_id=user.id, scope="")
    response = await rpc(mcp_http, "tools/list", token=tokens.access_token)
    assert response.status_code == 403
    assert response.json()["error"] == "insufficient_scope"


async def test_tools_list_exposes_the_full_surface(
    mcp_http: AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    _client, tokens = await mint_access_token(db_session, user_id=user.id)
    response = await rpc(mcp_http, "tools/list", token=tokens.access_token)
    assert response.status_code == 200
    names = {t["name"] for t in response.json()["result"]["tools"]}
    assert {"search_exercises", "log_session", "log_set", "get_prs", "get_volume_summary"} <= names
    assert {"get_active_session", "finish_session"} <= names  # Phase 11A lifecycle
    assert {"log_pr", "get_pr_history"} <= names  # manual PR entry
    assert {"update_session"} <= names  # post-hoc session correction
    # Corrections (docs/02 §Corrections): every write now has an undo, and the record tables
    # have a repair path. `restore` covers all four soft-deletable entity types.
    assert {"update_set", "update_custom_exercise", "update_pr"} <= names
    assert {
        "delete_set",
        "delete_session",
        "delete_custom_exercise",
        "delete_pr",
        "delete_pr_history_entry",
    } <= names
    assert {"recalculate_prs", "verify_pr_integrity", "restore", "purge_deleted"} <= names
    assert {"log_sets", "log_session_with_sets"} <= names  # transactional bulk writes
    assert len(names) == 33


async def test_guide_resource_readable(mcp_http: AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    _client, tokens = await mint_access_token(db_session, user_id=user.id)
    response = await rpc(
        mcp_http, "resources/read", {"uri": "tempo://guide"}, token=tokens.access_token
    )
    assert response.status_code == 200
    contents = response.json()["result"]["contents"]
    assert "Tempo — MCP tool guide" in contents[0]["text"]


async def test_search_returns_catalog(mcp_http: AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await make_global_exercise(db_session, slug="bench-press", name="Bench Press")
    _client, tokens = await mint_access_token(db_session, user_id=user.id)
    response = await rpc(
        mcp_http,
        "tools/call",
        {"name": "search_exercises", "arguments": {"query": "bench"}},
        token=tokens.access_token,
    )
    assert response.status_code == 200
    body = tool_result(response)
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Bench Press"


async def test_full_log_loop_with_pr_detection(
    mcp_http: AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    await make_global_exercise(db_session, slug="bench-press", name="Bench Press")
    _client, tokens = await mint_access_token(db_session, user_id=user.id)

    # Start a session…
    session = tool_result(
        await rpc(
            mcp_http,
            "tools/call",
            {"name": "log_session", "arguments": {"performed_at": "2026-07-22T18:00:00Z"}},
            token=tokens.access_token,
        )
    )
    session_id = session["id"]

    # …log a set, resolving the exercise by name (chat-identity rule)…
    logged = tool_result(
        await rpc(
            mcp_http,
            "tools/call",
            {
                "name": "log_set",
                "arguments": {
                    "session_id": session_id,
                    "exercise": "bench press",
                    "set_number": 1,
                    "weight_kg": 80,
                    "reps": 5,
                },
            },
            token=tokens.access_token,
        )
    )
    assert logged["set"]["is_pr"] is True
    assert logged["pr"]["is_pr"] is True  # first-ever log is a PR

    # …and read the PRs back.
    prs = tool_result(
        await rpc(
            mcp_http,
            "tools/call",
            {"name": "get_prs", "arguments": {}},
            token=tokens.access_token,
        )
    )
    assert any(p["exercise_name"] == "Bench Press" for p in prs["items"])


async def test_write_tool_requires_write_scope(
    mcp_http: AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    _client, tokens = await mint_access_token(db_session, user_id=user.id, scope="workouts.read")
    response = await rpc(
        mcp_http,
        "tools/call",
        {"name": "log_session", "arguments": {"performed_at": "2026-07-22T18:00:00Z"}},
        token=tokens.access_token,
    )
    assert response.status_code == 200  # transport ok; the tool itself refuses
    assert "workouts.write" in tool_error_text(response)


# ── The MCP surface stays off the REST cold path (docs/13 S1) ────────────────────────
def test_importing_the_app_does_not_import_the_mcp_sdk() -> None:
    """``import app.main`` must not pull in the MCP SDK — ~112 ms every REST cold start.

    Checked in a **subprocess**: by the time this suite runs, half the tests have imported
    ``app.mcp.server`` directly, so an in-process ``sys.modules`` check would be vacuous. The
    same reasoning covers the transitive heavyweights the SDK and the auth/image adapters drag
    in, each of which a REST request has no use for.
    """
    probe = (
        "import app.main, sys; "
        "leaked = [m for m in ('mcp', 'jsonschema', 'sse_starlette', 'uvicorn', 'httpx', "
        "'authlib') if m in sys.modules]; "
        "print(','.join(leaked))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "", f"leaked onto the REST import path: {result.stdout}"


async def test_the_runtime_boots_lazily_under_the_real_lifespan(db_session: AsyncSession) -> None:
    """The one test that runs the production wiring: FastAPI's lifespan, not a hand-run manager.

    Every other test here starts the session manager itself (``ASGITransport`` runs no
    lifespan), so this is what actually exercises ``asgi._LazyTransport`` — that boot leaves
    the MCP runtime unbuilt, an unauthenticated probe still doesn't build it, and the first
    authorized request does, then serves normally.
    """
    from app.main import create_app
    from app.mcp import runtime, server

    user = await make_user(db_session)
    _client, tokens = await mint_access_token(db_session, user_id=user.id)

    @asynccontextmanager
    async def _factory() -> AsyncIterator[Any]:
        yield db_session  # the fixture owns the transaction — never commit/close here

    runtime.set_session_factory(lambda: _factory())
    server.reset_session_manager()  # run() is one-shot per instance
    application = create_app()
    try:
        async with application.router.lifespan_context(application):
            assert not server.session_manager_started(), "boot must not build the MCP runtime"

            transport = ASGITransport(app=application)
            async with AsyncClient(transport=transport, base_url="http://localhost") as client:
                anonymous = await rpc(client, "tools/list")
                assert anonymous.status_code == 401
                assert not server.session_manager_started(), (
                    "an unauthenticated probe — most of what a public endpoint gets — "
                    "must be answered without booting the runtime"
                )

                authorized = await rpc(client, "tools/list", token=tokens.access_token)
                assert authorized.status_code == 200
                assert len(authorized.json()["result"]["tools"]) == 33
                assert server.session_manager_started()

                # Second call: the transport is already up, nothing restarts.
                assert (await rpc(client, "tools/list", token=tokens.access_token)).status_code == (
                    200
                )
    finally:
        runtime.reset_session_factory()
        server.reset_session_manager()


async def test_the_lifespan_exits_cleanly_when_mcp_is_never_touched() -> None:
    """A REST-only process must start and stop without ever booting MCP — or hanging.

    The parked worker has to be released on shutdown even though nothing ever woke it: that is
    the failure mode this design could plausibly have, and it would present as a deploy that
    never finishes draining. The request is a DB-free one so this stays a test about the
    lifespan and nothing else.
    """
    from app.main import create_app
    from app.mcp import server

    server.reset_session_manager()
    application = create_app()
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://localhost") as client:
            served = await client.get("/.well-known/oauth-authorization-server")
            assert served.status_code == 200
    assert not server.session_manager_started()


async def test_disallowed_host_rejected(mcp_http: AsyncClient, db_session: AsyncSession) -> None:
    # mcp_http keeps the session manager running; hit it with a spoofed Host header.
    from app.main import create_app

    user = await make_user(db_session)
    _client, tokens = await mint_access_token(db_session, user_id=user.id)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://evil.example") as bad_client:
        response = await rpc(bad_client, "tools/list", token=tokens.access_token)
    assert response.status_code == 421
