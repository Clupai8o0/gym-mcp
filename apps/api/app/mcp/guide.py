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
- **Retries are safe.** `log_session`, `log_set`, `log_sets`, `log_pr`, `plan_session`,
  `add_planned_sets` and `complete_planned_set` take an optional `client_key` — any string you can
  reproduce. A second call with the same key returns the first call's record instead of creating a
  duplicate. Use it whenever you are importing or backfilling.
- **Planned and logged are different things.** A prescribed set is an instruction; only a logged set
  counts toward volume, tonnage, frequency and records. See "Planning a workout" below.

## Session lifecycle
A session is **in progress** until it is finished — `ended_at` is `null`, and nothing about
the calendar date is involved. Before starting a new workout, call `get_active_session()`:
if it returns one, log into that instead of creating a duplicate. `finish_session(id)`
closes it and stores `duration_minutes`; it is safe to call twice. A session left open and
untouched for 12 hours is finished automatically the next time anything reads it, dated
from its last set.

## Planning a workout

`plan_session(performed_at, planned_sets=[...])` writes a workout **before** it happens: the session
and its prescription, one transaction. Each line takes `exercise` (UUID, slug or name),
`set_number`, and any of `target_reps_min`, `target_reps_max`, `target_weight_kg`, `target_rpe`,
`target_hold_seconds`, `notes`, `order_index`. Every target is optional — a line with none says "do
a set of this", which is a real instruction. Order is preserved, so a superset written A1, B1, A2,
B2 reads back that way.

**Nothing prescribed is training.** Planned sets live in their own table; they never move volume,
tonnage, frequency or a personal record. Work through the plan with
`complete_planned_set(planned_set_id, weight_kg=..., reps=...)`, which logs a **real set** (normal
PR detection, with a `pr` verdict in the result) and links it back to the line.

**Pass what you actually did.** Nothing is defaulted from the targets: a range of 8–10 has no single
right answer, and a plan recording its own targets as results would make adherence agree with itself.

You do not have to work through the plan to train. `log_set` still works for anything nobody
prescribed, and `session_progress(session_id)` reports it as `off_plan_count` rather than refusing
it — it also gives you planned vs completed counts, which movements still have work outstanding, and
`next_up`. `finish_session` returns the same counts as `adherence`; `percent` is `null` when the
session had no plan.

`performed_at` may be in the future — that is the normal case for a plan. A session dated for a
later day is **not** "in progress" and `get_active_session` will not return it until its start time
arrives; read it with `get_planned_session(session_id)` before then. Once it is the active session,
`get_active_session` carries `planned_total` and `completed_count` alongside `set_count`.

Deleting is symmetrical and never destroys the other half: `delete_planned_set` leaves the set it
recorded in the log (as off-plan work), and `delete_set` puts its prescribed line back to
outstanding. `update_planned_set` corrects the plan and never rewrites the log — for that, use
`update_set`.

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

- **A wrong number** — `update_set`, `update_session`, `update_planned_set`, `update_pr`,
  `update_custom_exercise`.
  Only the arguments you pass change. To empty a note rather than leave it, pass
  `clear_notes: true`: omitting an argument already means "leave alone".
- **Something that should not exist** — `delete_set`, `delete_session`, `delete_planned_set`,
  `delete_pr_history_entry`, `delete_pr`, `delete_custom_exercise`. All soft; `restore` undoes
  any of them (`entity_type` is `session`, `set`, `planned_set`, `exercise` or `pr_history_entry`). Deletes that would leave orphans refuse and say what to do: a session with sets
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
- **Planning:** `plan_session`, `add_planned_sets`, `get_planned_session`, `update_planned_set`,
  `delete_planned_set`, `complete_planned_set`, `session_progress`
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
