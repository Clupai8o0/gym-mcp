"""The ``/mcp`` Streamable-HTTP endpoint over the wire: OAuth guard + real tool calls.

Proves the mount works end-to-end (docs/04): unauthenticated/invalid/insufficient-scope
requests are rejected with the RFC 9728 pointer, and a valid bearer can list tools, read the
guide resource, and drive the full log-a-workout loop with PR detection — the same services
REST calls, reached through the MCP protocol.
"""

from __future__ import annotations

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
    assert len(names) == 15


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


async def test_disallowed_host_rejected(mcp_http: AsyncClient, db_session: AsyncSession) -> None:
    # mcp_http keeps the session manager running; hit it with a spoofed Host header.
    from app.main import create_app

    user = await make_user(db_session)
    _client, tokens = await mint_access_token(db_session, user_id=user.id)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://evil.example") as bad_client:
        response = await rpc(bad_client, "tools/list", token=tokens.access_token)
    assert response.status_code == 421
