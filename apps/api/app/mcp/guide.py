"""The ``tempo://guide`` resource text — a how-to-use-these-tools doc for a connected model.

Kept in sync with the tool set in :mod:`app.mcp.server` (docs/04). It is plain reference
prose, no logic, so it lives apart from the server wiring and the architecture guard leaves
it alone.
"""

from __future__ import annotations

GUIDE = """\
# Tempo — MCP tool guide

Tempo is a personal workout app: an illustrated exercise library, workout logging, and a
progress dashboard. These tools read and update **your own** training data; every call is
scoped to the account that authorized this connection.

## Conventions
- **IDs are UUIDs.** Where a tool takes `exercise` you may pass a UUID, an exact slug
  (`barbell-bench-press`), or a name (`Bench Press`) — it is resolved for you. Ambiguous
  names return the candidates so you can re-call with a specific id.
- **Units are metric and canonical:** weights in **kilograms**, holds/durations in
  **seconds**. Convert for display yourself; always send kg/seconds.
- **Times are ISO-8601** (`2026-07-22T18:30:00Z`), UTC canonical.
- **Reads** need the `workouts.read` scope; **writes** (`log_session`, `finish_session`,
  `log_set`, `create_custom_exercise`, `update_skill_progress`) need `workouts.write`.

## Session lifecycle
A session is **in progress** until it is finished — `ended_at` is `null`, and nothing about
the calendar date is involved. Before starting a new workout, call `get_active_session()`:
if it returns one, log into that instead of creating a duplicate. `finish_session(id)`
closes it and stores `duration_minutes`; it is safe to call twice. A session left open and
untouched for 12 hours is finished automatically the next time anything reads it, dated
from its last set.

## Typical workflow
1. `get_active_session()` → already training? Reuse that `session_id` and skip to step 3.
2. `search_exercises("bench press")` → find the movement and its id.
3. `log_session(performed_at=..., type="upper")` → start/record a session; keep its `id`.
4. `log_set(session_id, exercise="bench press", set_number=1, weight_kg=80, reps=5)` →
   log each set. The result includes a **PR verdict** (`pr.is_pr`, `pr.pr_type`) — celebrate
   personal records.
5. `finish_session(session_id)` → when the workout is over.
6. `get_session(session_id)` → review the session with its sets grouped by exercise.
7. `get_prs()` / `get_volume_summary(from, to)` / `get_session_frequency()` → progress.

## Tools
- **Library:** `search_exercises`, `get_exercise`, `create_custom_exercise`
- **Logging:** `log_session`, `get_active_session`, `finish_session`, `list_sessions`,
  `get_session`, `get_session_sets`, `log_set`
- **Records:** `get_prs`, `get_pr_history`, `log_pr`
- **Analytics:** `get_volume_summary`, `get_session_frequency`
- **Skills (calisthenics tree):** `get_skill_overview`, `get_skill_detail`,
  `update_skill_progress`

Set metrics are optional but you must supply at least one of `weight_kg`, `reps`, or
`hold_seconds`. Weight PRs require both weight and reps on the set.

`log_set` detects PRs from what was actually lifted. Use `log_pr` for a record that has no set
behind it — an estimated 1RM, a hold timed outside a session, or a PR brought over from another
app. A hand-entered record wins immediately; a later logged set only replaces it by beating it.
"""
