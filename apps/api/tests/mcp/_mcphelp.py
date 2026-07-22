"""Helpers for the MCP tests: a JSON-RPC caller and a direct-tool binding context.

Two ways to exercise the tools:
- **Over the wire** (:func:`rpc`, :func:`tool_result`) — drive the real Streamable-HTTP
  endpoint, proving the mount + OAuth guard + protocol work end-to-end.
- **In-process** (:func:`bound`) — bind a principal + the rolled-back test session, then call
  a tool function directly. The MCP↔REST contract tests use this to compare tool output to the
  REST sibling with no transport in the way.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from typing import Any, cast

from app.mcp import runtime
from app.services.oauth import TokenPrincipal
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

# Streamable-HTTP requires the client accept both JSON and the SSE fallback.
MCP_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
FULL_SCOPES = frozenset({"workouts.read", "workouts.write"})


async def rpc(
    client: AsyncClient,
    method: str,
    params: Mapping[str, Any] | None = None,
    *,
    token: str | None = None,
    request_id: int = 1,
) -> Response:
    """POST a single JSON-RPC request to ``/mcp`` (optionally bearer-authenticated)."""
    headers = dict(MCP_HEADERS)
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params or {})}
    return await client.post("/mcp", json=body, headers=headers)


def tool_result(response: Response) -> dict[str, Any]:
    """Extract a tool call's returned object from a JSON-RPC response (raises on tool error)."""
    payload = response.json()
    assert "error" not in payload, f"JSON-RPC error: {payload['error']}"
    result = payload["result"]
    assert not result.get("isError"), f"tool error: {result.get('content')}"
    structured = result.get("structuredContent")
    if structured is not None:
        return cast("dict[str, Any]", structured)
    text = result["content"][0]["text"]
    return cast("dict[str, Any]", json.loads(text))


def tool_error_text(response: Response) -> str:
    """The error message a failed tool call surfaced (its text content)."""
    result = response.json()["result"]
    assert result.get("isError"), "expected a tool error"
    return "".join(block.get("text", "") for block in result["content"])


@contextmanager
def bound(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    *,
    scopes: frozenset[str] = FULL_SCOPES,
) -> Iterator[None]:
    """Bind a principal + point the tool/auth session at ``db_session`` (in-process calls)."""

    @asynccontextmanager
    async def _factory() -> Any:
        yield db_session  # the fixture owns the transaction — never commit/close here

    runtime.set_session_factory(lambda: _factory())
    principal = TokenPrincipal(user_id=user_id, client_id="test-client", scopes=scopes)
    try:
        with runtime.bind_principal(principal):
            yield
    finally:
        runtime.reset_session_factory()
