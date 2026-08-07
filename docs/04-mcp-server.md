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
| `get_active_session` | `sessions.get_active_session` | The in-progress session, or `null`; carries `set_count` + `planned_total`/`completed_count` (11A/11N) |
| `finish_session` | `sessions.finish_session` | End a session, store its duration, report adherence (11A/11N) |
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

### Corrections (Phase 11L) — the other half of the write path

Tempo was append-only in practice: every write was permanent, so a bug that wrote
`duration_minutes = 136070` or a stray history row could never be taken back. These tools make
removal a correction rather than a second irreversible act. **Every delete is soft** — the row
leaves all reads and `restore` brings it back; `purge_deleted` is the only path that frees the
storage, and it must be asked for explicitly.

| Tool | Service | Notes |
|---|---|---|
| `log_sets` | `sets.log_sets` | Many sets into one session, one transaction |
| `log_session_with_sets` | `sessions.create` + `sets.log_sets` | A whole workout, one transaction |
| `update_set` | `sets.update_set` | Recalculates that exercise's records |
| `delete_set` | `sets.delete_set` | Soft; the record falls back to next best |
| `delete_session` | `sessions.delete` | `cascade`; refuses with a count otherwise |
| `update_custom_exercise` | `exercises.update_custom` | Rename keeps the old slug as an alias |
| `delete_custom_exercise` | `exercises.delete_custom` | `reassign_to` or it refuses — never orphan sets |
| `update_pr` | `prs.update_pr` | Hand-entered records only |
| `delete_pr` | `prs.delete_pr` | Withdraws the claim; next best becomes current |
| `delete_pr_history_entry` | `prs.delete_history_entry` | Removes one chronology entry |
| `recalculate_prs` | `integrity.recalculate` | Rebuilds records from ground truth |
| `verify_pr_integrity` | `integrity.verify` | Read-only; the CI/post-migration assertion |
| `restore` | `corrections.restore` | Undo for any soft delete |
| `purge_deleted` | `corrections.purge` | Irreversible; ≥1 day window |

Three conventions run through all of them:

- **`client_key`** on `log_session`, `log_set`, `log_sets` and `log_pr` makes a retry idempotent.
  A repeat with the same key returns the original record — the failure that once left two
  identical `upper_hypertrophy` sessions dated 1 May.
- **`dry_run`** on destructive and bulk calls reports what would change and changes nothing.
- **`clear_notes`** rather than a nullable `notes`: in a partial update `null` already means
  "leave alone", so emptying a field needs its own word.

Records are **derived state**, and the tools say so instead of pretending otherwise: `update_pr`
and `delete_pr` refuse an auto-detected record and point at the set behind it, because the next
recalculation would undo any edit made here.

### Planning (Phase 11N) — a session before it happens

A session could only hold sets that had already happened, so a coach-written plan had nowhere to
live: the only way to say "5×5 at 100 kg on Tuesday" was to log five sets nobody had done. These
tools add the prescription alongside the log.

**Nothing prescribed is training.** Planned sets live in their own table (`planned_sets`, docs/02
§Planning) and no analytics or PR query joins it, so a plan cannot move volume, tonnage, frequency
or a personal record however it is written. `complete_planned_set` is the single door between the
two: it calls `sets.log_set` — the same write everything else makes, PR detection and all — and
records that set's id against the line.

| Tool | Service | Notes |
|---|---|---|
| `plan_session` | `plans.plan_session` | Session + prescription, one transaction; `performed_at` may be in the future |
| `add_planned_sets` | `plans.add_planned_sets` | Append lines; all or nothing, names the bad index |
| `get_planned_session` | `plans.get_plan` | The plan in performance order + each line's completion state |
| `update_planned_set` | `plans.update_planned_set` | Corrects the plan; never rewrites the log |
| `delete_planned_set` | `plans.delete_planned_set` | Soft; a set logged against it stays, as off-plan work |
| `complete_planned_set` | `plans.complete` | Logs what was actually done and links it; returns the PR verdict |
| `session_progress` | `plans.progress` | Planned vs completed, remaining movements, next up |

Four conventions specific to this family:

- **Pass what happened, not what was prescribed.** `complete_planned_set` defaults nothing from the
  targets. A range of 8–10 has no single right answer, and a plan recording its own targets as
  results would make adherence a number that agrees with the plan by construction.
- **Off-plan work is never blocked.** `log_set` still works for anything nobody prescribed;
  `session_progress` reports it as `off_plan_count` rather than refusing it.
- **Completion is derived.** A line is done while the set it names is live — `delete_set` reopens it
  with nothing to re-sync, and `delete_planned_set` leaves the training exactly where it is.
- **`percent` is `null` when nothing was prescribed.** On a session logged without a plan, both 0%
  and 100% would be claims about a prescription that never existed.

A **future-dated** session is a plan waiting for its day: it is not returned by
`get_active_session` until its start time arrives (see D36), so read it with
`get_planned_session`. `client_key` works on `plan_session`, `add_planned_sets` and
`complete_planned_set` exactly as it does elsewhere.

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
