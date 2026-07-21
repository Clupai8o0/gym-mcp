# 04 — MCP Server (Python)

The MCP server is a **thin adapter** over `services/`, mounted inside the same FastAPI app so
it shares the process, the DB engine, and the exact business logic that REST uses. This is the
"one Python brain" made concrete: **a tool is ~10 lines that validates args and calls a service.**

## SDK & transport

- Use the official **Python MCP SDK** (`mcp`), `FastMCP` high-level API.
- Transport: **Streamable HTTP** (stateless), matching how claude.ai talks to remote servers
  and how the current app works. No SSE-only legacy transport.
- Mount the MCP ASGI app into FastAPI at **`/mcp`** (public URL `https://api.tempo.clupai.com/mcp`).
  Example wiring:

```python
# app/mcp/server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tempo")

# ... tool registrations (below) ...

# app/main.py
from app.mcp.server import mcp
app.mount("/mcp", mcp.streamable_http_app())
```

> Confirm the exact mount/app-factory call against the installed SDK version during Phase 5;
> the SDK's HTTP-app accessor name has changed across versions. The **pattern** — mount the
> streamable-HTTP ASGI app at `/mcp` — is stable.

## Authentication

The MCP endpoint is an **OAuth 2.0 protected resource** (see `05-auth-oauth.md`):
- Unauthenticated requests get **401** with a `WWW-Authenticate` header pointing at the
  Protected Resource Metadata URL (RFC 9728).
- Authenticated requests carry `Authorization: Bearer <tempo access token>`. A dependency/
  middleware resolves the token → `user_id` (via `oauth_access_tokens`), and every tool call
  runs scoped to that user.
- The same `resolve_bearer_user()` helper used by REST's `current_user()` is reused here — no
  second auth path.

## Tool ↔ service mapping

Every tool maps to a service function. **No tool contains domain logic.** The set mirrors the
REST surface plus catalog search, so chat and UI have parity.

| MCP tool | Service | Purpose |
|---|---|---|
| `search_exercises` | `exercises.list` | Find catalog exercises by name/muscle/equipment |
| `get_exercise` | `exercises.get` | Full detail incl. `illustration_url` |
| `create_custom_exercise` | `exercises.create_custom` | Add a user's own movement |
| `log_session` | `sessions.create` | Start/record a session |
| `get_session` | `sessions.get` | Session + sets grouped by exercise |
| `list_sessions` | `sessions.list` | Filter by type/date |
| `log_set` | `sets.log_set` | Log a set; auto PR detection |
| `get_session_sets` | `sessions.get` | (or dedicated) sets for a session |
| `get_prs` | `prs.list` | PRs, optional exercise filter |
| `get_pr_history` | `prs.history` | Chronological PRs for exercise+type |
| `update_skill_progress` | `skills.upsert_progress` | Secondary module |
| `get_skill_overview` | `skills.overview` | All skills + progress |
| `get_skill_detail` | `skills.detail` | One skill + total stages |
| `get_volume_summary` | `analytics.volume` | Sets/reps/tonnage by exercise for a range |
| `get_session_frequency` | `analytics.frequency` | Sessions per ISO week |

### Tool template

```python
@mcp.tool()
async def log_set(
    session_id: str,
    exercise_id: str,
    set_number: int,
    weight_kg: float | None = None,
    reps: int | None = None,
    hold_seconds: int | None = None,
    rpe: float | None = None,
    notes: str | None = None,
    ctx: Context = ...,
) -> dict:
    """Log a single set for a session. Auto-detects personal records."""
    user_id = current_mcp_user(ctx)          # from the bearer token
    async with get_session() as db:
        result = await services.sets.log_set(
            db, user_id=user_id, session_id=UUID(session_id),
            exercise_id=UUID(exercise_id), set_number=set_number,
            weight_kg=weight_kg, reps=reps, hold_seconds=hold_seconds,
            rpe=rpe, notes=notes,
        )
    return result.model_dump()
```

## Resources

Expose a **guide resource** (like the current `gym://guide`) so a connected model gets a
concise how-to-use-these-tools document. Keep it in sync with the tool list above.

- `tempo://guide` — markdown reference: tool catalog, argument conventions (IDs are UUIDs,
  units are kg/seconds), typical workflows ("start a session, then log sets").
- Optionally `tempo://exercise/{slug}` — read an exercise's detail as a resource.

## Exercise identity in chat

Chat users say names ("bench press"), not UUIDs. Handle this by making `search_exercises` the
natural first step and having `log_set` accept a UUID from that search. To reduce round-trips,
`log_set` MAY also accept an `exercise_slug` or `exercise_name` that the service resolves to an
id (global catalog first, then the user's customs; ambiguous → return candidates). Decide the
exact resolution rule in Phase 5 and document it in the guide resource.

## claude.ai connector verification (Phase 5 exit test)

1. Deploy `api` so `https://api.tempo.clupai.com/mcp` is reachable.
2. In claude.ai → Settings → Connectors → add custom connector with the MCP URL
   (`https://api.tempo.clupai.com/mcp`).
3. Confirm the OAuth handshake completes (discovery → DCR → Google login → token) — see `05`.
4. In a chat: "search for bench press", "start an upper session today", "log 3×5 at 80 kg",
   "what are my bench PRs?" — verify data appears in Neon and in the web UI.
5. Confirm an expired access token triggers a refresh (rotation) without user re-auth.

## Definition of Done (MCP phase)
- All tools above registered, each ≤ ~15 lines, each calling a service (verified by the
  contract test in `03`).
- `/mcp` is OAuth-protected; unauthenticated calls return 401 + `WWW-Authenticate` PRM pointer.
- The claude.ai connector completes the handshake and the five verification prompts succeed
  end-to-end against production (or a preview with a Neon branch).
