# HANDOVER: planned (prescribed) sets, Phase 11N

**Status: committed and pushed to `main` on 2026-08-07. Not yet deployed.**

Deploying it is **not** just `vercel --prod`. Since this phase the API queries `planned_sets` from
`analytics.frequency`, `sessions.get_active_session`, `exercises.delete_custom` and
`corrections.purge`, so shipping the code before its table exists returns 500s on the dashboard
rather than degrading quietly. Migration `0008` has to run against production Neon **first**. See
`docs/STATUS.md`, Phase 10, "Deploying a migration".

Full detail lives in `docs/STATUS.md` under **Phase 11N**. This file is the short version plus the
things you cannot read off the diff: how to run it, what is deliberately unfinished, and where the
traps are.

---

## 0. Where things stand

The feature is complete and green. 353 tests pass (up from 296), `ruff` + `black` +
`mypy --strict` are clean, `pnpm exec turbo run build lint typecheck test` is 7/7, and
`alembic check` reports no drift.

Two adversarial review passes ran over it. The first (34 agents, six lenses) confirmed seven real
defects; the second (three agents, over the fixes themselves) confirmed two more that the first
round's fixes had introduced. All nine are fixed and each has a regression test named after the
failure rather than the fix. The full list, including what was refuted and why, is in
`docs/STATUS.md` under "Found by adversarial review".

**Nothing is known-broken.** The open items in section 5 are choices, not bugs.

---

## 1. Getting it running

Local Postgres 16 (Homebrew) is already running as role `clupa`. There is no `postgres` role on
this machine, which matters:

```bash
cd apps/api

# The one gotcha. `uv run` does NOT load .env, and tests/_dbadmin.py reads os.environ
# directly (not through pydantic Settings), so it falls back to a `postgres` role that
# does not exist here. Bare `uv run pytest` fails at fixture setup with
# `role "postgres" does not exist`. Always export it:
TEST_DATABASE_URL=postgresql://clupa@localhost:5432/postgres uv run pytest -q

uv run ruff check . && uv run black --check .
uv run mypy
```

From the repo root, the whole monorepo check (`turbo` passes `TEST_DATABASE_URL` through):

```bash
TEST_DATABASE_URL=postgresql://clupa@localhost:5432/postgres pnpm exec turbo run build lint typecheck test
```

Migration and drift check against a throwaway database:

```bash
psql "postgresql://clupa@localhost:5432/postgres" -qtAc 'create database tempo_scratch'
cd apps/api
DATABASE_URL=postgresql://clupa@localhost:5432/tempo_scratch \
DATABASE_URL_UNPOOLED=postgresql://clupa@localhost:5432/tempo_scratch \
  uv run alembic upgrade head && \
DATABASE_URL=postgresql://clupa@localhost:5432/tempo_scratch \
DATABASE_URL_UNPOOLED=postgresql://clupa@localhost:5432/tempo_scratch \
  uv run alembic check
psql "postgresql://clupa@localhost:5432/postgres" -qtAc 'drop database tempo_scratch with (force)'
```

**Warning:** `alembic upgrade head` run from `apps/api` without explicit `DATABASE_URL` env vars
falls through to `.env` and will advance your local **`tempo_dev`** database. That already happened
once during review. `tempo_dev` is currently at head (`0008`), which is where it belongs, but be
deliberate about it.

Regenerating the API spec and the web types after any schema change (both artifacts are committed):

```bash
cd apps/api
DATABASE_URL=postgresql://localhost:5432/x DATABASE_URL_UNPOOLED=postgresql://localhost:5432/x \
  uv run python -c "
import json
from app.main import create_app
spec = create_app().openapi()
with open('../web/openapi.json','w') as f:
    json.dump(spec, f, indent=2); f.write('\n')
"
cd ../web && pnpm gen:api
```

---

## 2. What was built

### New files

| File | What it is |
|---|---|
| `apps/api/app/models/planned_set.py` | The `PlannedSet` model |
| `apps/api/migrations/versions/0008_planned_sets.py` | One new table, nothing altered |
| `apps/api/app/services/plans.py` | The only writer of the table. All the domain logic |
| `apps/api/app/schemas/plans.py` | Pydantic I/O |
| `apps/api/app/api/routers/planned_sets.py` | `/api/planned-sets/*` |
| `apps/api/tests/services/test_plans.py` | 40 tests, including `TestAPlanIsNotTraining` |
| `apps/api/tests/routers/test_planned_sets.py` | The REST loop end to end |

### Modified

`services/sessions.py` (scheduling skew, adherence on finish, plan cascade), `services/sets.py`
(one public helper), `services/corrections.py` (`planned_set` entity, purge guard),
`services/exercises.py` (delete_custom counts prescriptions), `services/analytics.py` (the two
counting fixes), `schemas/sessions.py`, `schemas/exercises.py`, `api/routers/sessions.py`,
`api/routers/exercises.py`, `main.py`, `mcp/server.py`, `mcp/guide.py`, plus tests and
`apps/web/openapi.json` + `lib/api-types.ts`.

### The seven new MCP tools (33 to 40), each with a REST twin

`plan_session`, `add_planned_sets`, `get_planned_session`, `update_planned_set`,
`delete_planned_set`, `complete_planned_set`, `session_progress`.

Plus: `finish_session` now returns adherence, `get_active_session` carries
`planned_total`/`completed_count`, `restore` gained a fifth entity type (`planned_set`), and
`delete_session`/`delete_custom_exercise` report `planned_count`.

---

## 3. The five load-bearing ideas

Read these before changing anything in `services/plans.py`. Each is documented at length in the
module docstrings and in `docs/02-data-model.md` under "Planning (Phase 11N)".

1. **A prescription is never training.** Planned rows live in their own table and no analytics or
   PR query joins it, so the invariant holds by construction rather than by six queries remembering
   a filter. `plans.complete` is the single door across, and it writes through `sets.log_set` (the
   same call the log button makes) rather than a second write path that could drift.

2. **Completion is derived, not stored.** A line is done while the set it names is *live*. Deleting
   that set reopens the line with no second write and no way for the two to disagree.

3. **Off-plan work is never blocked.** Nothing gates `log_set`. `session_progress` reports it as
   `off_plan_count`.

4. **A future-dated session has not started.** `plan_session` is the first thing in Tempo that
   dates a session ahead of now, and the D31 lifecycle only ever looked backwards. See
   `sessions.SCHEDULING_SKEW` and decision **D36**.

5. **Adherence is `null`, not `0`, when nothing was prescribed.** Both 0% and 100% would be claims
   about a plan that never existed.

### Two subtleties that are easy to undo by accident

- **`planned_sets_completed_set_uidx` is partial on `completed_set_id IS NOT NULL AND deleted_at IS
  NULL`.** Both halves matter, and the predicate must stay identical to the filter in
  `plans._claimant`. Dropping the `deleted_at` half makes the index (not the service) refuse the
  next completion, turning a domain conflict into a 500. Adding it back is what forced
  `corrections.restore` to release a restored line's claim when the set has been taken in the
  meantime. `alembic check` compares neither CHECK-constraint names nor partial-index predicates,
  so `tests/test_migrations.py` asserts both against the DDL a real database ships.

- **`analytics.frequency` asks whether a session was *ever* a prescription** (deleted lines
  included). Keying it on live lines means deleting the last line of a plan you never started
  *raises* your training count from 0 to 1.

---

## 4. What is explicitly NOT done

- **Not deployed.** Committed and pushed, but production still runs API **0.5.0 / 38 paths**. The
  migration gate above is why. (The landing-page illustration work that shared this working tree
  went out as its own commit, as suggested here originally.)

- **No web UI.** This is API plus MCP only. Nothing in `apps/web` renders a plan. That is the
  natural next phase, and it is where the flagged dashboard filter below gets fixed.

- **Not run against Neon.** Verified on local Postgres 16 only, which is the repo's standing rule
  (an empty local database is equivalent to an empty Neon branch). Neon provisioning is still the
  outstanding Phase 1 external prerequisite.

- **Not driven through a real claude.ai connector.** The MCP tools are exercised in-process and
  over the real Streamable-HTTP transport in tests, but no live connector handshake was run (that
  gate is still blocked on the Google OIDC prerequisite).

---

## 5. Open items for whoever picks this up

1. **The em-dash style conflict.** Your recorded preference is no em dashes in prose, code
   comments, or docs. This repo's existing voice uses them heavily (every service docstring, both
   prior HANDOVER files, `docs/02`), and this session's ~1500 new lines matched that voice. So the
   new code is stylistically consistent with the repo and inconsistent with your preference. Decide
   which wins. A sweep across the new files only is maybe 30 minutes; a repo-wide sweep is a much
   larger, noisier diff. This file is written without them.

2. **`apps/web/app/(app)/dashboard/page.tsx:144`** filters recent sessions with
   `performed_at >= weekFrom` and no upper bound, so a session planned for later this week counts
   toward the home "sessions this week" tile and appears in the `DayStrip`. It is a client-side
   filter over `/api/sessions`, not an API number (`analytics.frequency` is now correct). One-line
   fix, best done in the phase that builds the planning UI.

3. **An adjacent bug was fixed without being asked for.** `analytics.volume` and
   `analytics.frequency` never filtered `deleted_at`, so a deleted session's tonnage stayed in every
   total permanently. It is two predicates plus tests, and it sits on the same line of code as the
   required frequency fix, but it does change long-standing behaviour. Reverting it is
   straightforward if you would rather it landed separately: see the `deleted_at` filters in
   `services/analytics.py` and the two tests at the bottom of `tests/services/test_analytics.py`.

4. **`corrections.purge` now skips an exercise that anything still references** rather than
   attempting the `DELETE` and raising a foreign-key violation. This also closes the identical
   pre-existing hole for `exercise_sets`. Worth a second opinion on whether skipping (rather than
   cascading) is the behaviour you want long term.

5. **Decisions D36 and D37** were appended to the log in `docs/01-architecture.md`. They record the
   scheduling-skew rule and the frequency-counting rule. Both are the kind of thing a future phase
   might want to revisit, and neither has been reviewed by a human yet.

---

## 6. Reference

- **Live state:** `docs/STATUS.md`, Phase 11N (scope, the full review findings, DoD evidence).
- **Schema and the "why":** `docs/02-data-model.md`, the `planned_sets` table plus the
  "Planning (Phase 11N)" section.
- **REST surface:** `docs/03-backend-fastapi.md`, the surface table.
- **MCP tools:** `docs/04-mcp-server.md`, the "Planning (Phase 11N)" family.
- **Decision log:** `docs/01-architecture.md`, D36 and D37.
- **What a connected model is told:** `apps/api/app/mcp/guide.py`, the "Planning a workout"
  section (this ships to claude.ai, so keep it true).
- **Project guardrails:** `CLAUDE.md` and `docs/12-conventions.md`. The two that bit hardest here:
  REST and MCP stay in lockstep (a contract test enforces it), and no business logic outside
  `services/` (an architecture test greps for it).
