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
- **Reads** need the `workouts.read` scope; **writes** (`log_session`, `log_set`,
  `create_custom_exercise`, `update_skill_progress`) need `workouts.write`.

## Typical workflow
1. `search_exercises("bench press")` → find the movement and its id.
2. `log_session(performed_at=..., type="upper")` → start/record a session; keep its `id`.
3. `log_set(session_id, exercise="bench press", set_number=1, weight_kg=80, reps=5)` →
   log each set. The result includes a **PR verdict** (`pr.is_pr`, `pr.pr_type`) — celebrate
   personal records.
4. `get_session(session_id)` → review the session with its sets grouped by exercise.
5. `get_prs()` / `get_volume_summary(from, to)` / `get_session_frequency()` → progress.

## Tools
- **Library:** `search_exercises`, `get_exercise`, `create_custom_exercise`
- **Logging:** `log_session`, `list_sessions`, `get_session`, `get_session_sets`, `log_set`
- **Records:** `get_prs`, `get_pr_history`
- **Analytics:** `get_volume_summary`, `get_session_frequency`
- **Skills (calisthenics tree):** `get_skill_overview`, `get_skill_detail`,
  `update_skill_progress`

Set metrics are optional but you must supply at least one of `weight_kg`, `reps`, or
`hold_seconds`. Weight PRs require both weight and reps on the set.
"""
