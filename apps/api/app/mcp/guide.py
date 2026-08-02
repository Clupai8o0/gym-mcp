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
- **Reads** need the `workouts.read` scope; every **write**, **correction** and **delete** needs
  `workouts.write`.
- **Nothing you write is permanent.** Every delete is soft: the row leaves all reads and
  `restore(entity_type, id)` brings it back. Only `purge_deleted` erases anything for good.
- **Retries are safe.** `log_session`, `log_set`, `log_sets` and `log_pr` take an optional
  `client_key` — any string you can reproduce. A second call with the same key returns the first
  call's record instead of creating a duplicate. Use it whenever you are importing or backfilling.

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

## Backfilling training history
Use `log_session_with_sets` — one call per workout, one transaction, so a session can never end
up with half its sets. `log_sets` does the same for sets into a session that already exists.
Both take the same set shape as `log_set` and return a PR verdict for every row.

Give each call a `client_key` so a retry cannot duplicate it. And set `is_backfill: true` on
sets you are entering after the fact rather than measuring: they still count toward volume and
frequency, but they are kept out of PR detection — a placeholder `reps: 1` should not become a
reps record of 1.

## Fixing things
Every write has an undo, and nothing needs the delete-and-reinsert dance:

- **A wrong number** — `update_set`, `update_session`, `update_pr`, `update_custom_exercise`.
  Only the arguments you pass change. To empty a note rather than leave it, pass
  `clear_notes: true`: omitting an argument already means "leave alone".
- **Something that should not exist** — `delete_set`, `delete_session`,
  `delete_pr_history_entry`, `delete_pr`, `delete_custom_exercise`. All soft; `restore` undoes
  any of them. Deletes that would leave orphans refuse and say what to do: a session with sets
  needs `cascade: true`; a custom exercise with sets needs `reassign_to`.
- **Records that look wrong** — `verify_pr_integrity()` reports any exercise whose chronology
  steps downward or whose record disagrees with it; `recalculate_prs()` rebuilds from the live
  sets and hand-entered claims. Corrections do this automatically for what they touch, so call
  it directly only to repair data a past bug already left broken.
- **Destructive or bulk calls take `dry_run: true`** — it reports what would change and changes
  nothing. Worth doing first when you are acting on someone's training history.

Records are **derived**, and the tools say so rather than pretending: an auto-detected record
describes a set that exists, so `update_pr`/`delete_pr` refuse it and point you at the set.

## Tools
- **Library:** `search_exercises`, `get_exercise`, `create_custom_exercise`,
  `update_custom_exercise`, `delete_custom_exercise`
- **Logging:** `log_session`, `log_session_with_sets`, `update_session`, `delete_session`,
  `get_active_session`, `finish_session`, `list_sessions`, `get_session`, `get_session_sets`,
  `log_set`, `log_sets`, `update_set`, `delete_set`
- **Records:** `get_prs`, `get_pr_history`, `log_pr`, `update_pr`, `delete_pr`,
  `delete_pr_history_entry`
- **Integrity:** `recalculate_prs`, `verify_pr_integrity`, `restore`, `purge_deleted`
- **Analytics:** `get_volume_summary`, `get_session_frequency`
- **Skills (calisthenics tree):** `get_skill_overview`, `get_skill_detail`,
  `update_skill_progress`

Set metrics are optional but you must supply at least one of `weight_kg`, `reps`, or
`hold_seconds`. Weight PRs require both weight and reps, and a **`weight_kg` of 0 is not a
load** — bodyweight and assisted work progress on reps.

Recording a past workout? Give `log_session` its real `performed_at` (and `duration_minutes`
if known) and it is stored already finished — only a session started just now stays "in
progress".

`log_set` detects PRs from what was actually lifted. Use `log_pr` for a record with no set
behind it — an estimated 1RM, a hold timed outside a session, a PR brought from another app. It
has to **beat the record standing at its own moment**, exactly as a set does, which is what keeps
PR history monotonic; backdating still works, since a claim dated January is judged against
January. To change a record you already have, use `update_pr` — that is a correction, not a new
achievement.
"""
