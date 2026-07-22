# STATUS — live state tracker

The orchestrator's source of truth for "where are we" (see
[`11-agent-workflow.md`](./11-agent-workflow.md)). One section per phase; update at the end of
each phase with what shipped, DoD evidence, and any decisions.

**Legend:** `NOT STARTED` · `IN PROGRESS` · `BLOCKED` · `DONE`

---

## External prerequisites (needed before later phases)

Not required for Phase 0. Track here so they don't become surprise blockers:

- [ ] Neon project (primary + preview branch); pooled + unpooled URLs — **Phase 1**
      ⤷ schema + migrations are built and verified (against local Postgres 16); **provisioning the
      Neon project and setting `DATABASE_URL`/`DATABASE_URL_UNPOOLED` is the one remaining step** —
      then `pnpm --filter @tempo/api migrate` applies `head` to the Neon branch.
- [ ] Google OAuth client (OIDC) + authorized redirect URI — **Phase 3**
- [ ] Vercel Blob store (`BLOB_READ_WRITE_TOKEN`) — **Phase 4**
- [ ] OpenAI API key + GPT Image 2 access — **Phase 4**
- [ ] Domain / DNS for `tempo.clupai.com` + `api.tempo.clupai.com`; two Vercel projects — **Phase 10**

---

## Phase 0 — Repo & tooling foundation — DONE
- **Branch/PR:** `phase-0-foundation` (committed locally; push + PR pending human go-ahead)
- **Scope:** pnpm + Turborepo monorepo; `apps/web` (Next.js) boots "hello"; `apps/api` (FastAPI,
  uv) boots with `GET /api/health`; shared TS config + ESLint config packages; root tooling
  (ruff/black/mypy, eslint/prettier/tsc-strict, pytest); Conventional-Commit + PR templates;
  `.env.example`; `.gitignore`; CI (lint+type+test+build). Old TS/Supabase app archived to
  `legacy/`.
- **DoD evidence:**
  - `pnpm exec turbo run build lint typecheck test` → **7/7 tasks successful** (web:
    build+lint+typecheck; api: build+lint+typecheck+test). Web `next build` compiles + typechecks +
    prerenders `/`; web ESLint + `tsc --noEmit` clean; api `ruff` + `black --check` + `mypy`
    (strict) clean; api `pytest` 1 passed.
  - **Both apps boot locally:** `uvicorn app.main:app` → `GET /api/health` = `{"status":"ok"}`;
    `next start` → `GET /` returns "Hello world!" (200).
  - **CI:** `.github/workflows/ci.yml` added (install → uv sync → `turbo run build lint typecheck
    test`, plus a commitlint job on PRs). Runs on push/PR — not yet executed (branch not pushed).
- **Notes / decisions:**
  - Toolchain resolved ahead of the docs' assumptions: **Next 16 / React 19.2 / TypeScript 5
    (via create-next-app pin) / ESLint 9**; **Turbo 2.10**; **uv 0.11 / Python 3.13**.
  - Old TS/Supabase app moved to `legacy/` via `git mv` (history preserved, read-only) — see
    `legacy/ARCHIVE_NOTE.md`. Reversible.
  - `packages/ui` deferred until it's first needed (Phase 6).

## Phase 1 — Neon + data model — DONE (verified on local Postgres; Neon provisioning pending)
- **Branch/PR:** `phase-1-data-model` (cut from `phase-0-foundation` HEAD, since Phase 0 is not
  yet merged to `main`; committed locally, push + PR pending human go-ahead).
- **Scope:**
  - **SQLAlchemy 2.0 models** (`app/models/`) for all 7 core + skills tables — `users`,
    `exercises`, `workout_sessions`, `exercise_sets`, `personal_records`, `skills`,
    `skill_progress` — mirroring `docs/02-data-model.md`. OAuth tables deferred to Phase 3.
  - **Alembic** (async `env.py`, uses the **unpooled** URL): `0001_init` creates the
    `pgcrypto` + `pg_trgm` extensions and every table with its indexes — incl. the partial-unique
    slug indexes, the `primary_muscles` GIN index, and the `name gin_trgm_ops` trigram index —
    and all CHECK constraints. `0002_seed_skills` seeds the 13 skills.
  - **`core/config.py`** (pydantic-settings: pooled + unpooled URLs) and **`core/db.py`**
    (async engine/sessionmaker + `make_asyncpg_url` — Neon-safe: forces `+asyncpg`, lifts
    `sslmode`→`ssl`, drops libpq-only params).
  - **Test harness** (`tests/conftest.py`, `tests/_dbadmin.py`): a session-scoped migrated
    schema + a per-test transaction-rollback `AsyncSession`.
  - CI Postgres 16 service; `.env.example` `TEST_DATABASE_URL`; `migrate` / `migrate:down` /
    `migrate:make` scripts on `@tempo/api`.
- **DoD evidence:**
  - **`alembic upgrade head`** on an empty DB → all 7 core+skills tables (+ `alembic_version`),
    `pgcrypto` + `pg_trgm`, 13 skills seeded. Spot-checked DDL: `exercises_name_trgm` =
    `USING gin (name gin_trgm_ops)`; `exercises_global_slug_uidx` = unique btree `WHERE
    (created_by_user_id IS NULL)`.
  - **`alembic downgrade base`** → every table + both extensions removed (only `alembic_version`
    remains); **re-`upgrade head` is repeatable** (re-seeds 13).
  - **`uv run pytest -q` → 20 passed:** model round-trips for every table (server defaults, arrays,
    Decimal, timestamps); partial-index behavior (two globals same slug conflict; global+custom
    same slug allowed); `unit_pref` CHECK; migration up/down/up reversibility; skills-seeded;
    `make_asyncpg_url` URL parsing.
  - **`pnpm exec turbo run build lint typecheck test` → 7/7 successful.** API `ruff` + `black
    --check` + `mypy` (strict, 21 files) clean.
  - **`.env`-based `alembic upgrade head`** (the `pnpm migrate` path) verified via the settings
    fallback in `env.py`.
- **Notes / decisions:**
  - **Skills seeded via an Alembic data migration (`0002`)** rather than a `scripts/` seed —
    they're fixed reference data, so `alembic upgrade head` yields a fully-seeded DB on any fresh
    branch with no extra step. (The ~800-row **catalog** seed remains a Phase 4 script, per the docs.)
  - Verified against **local Postgres 16** (an empty DB ≡ an empty Neon branch, per `12`'s test
    rule). **Provisioning the actual Neon project + wiring pooled/unpooled URLs is the sole
    remaining external prerequisite** — flagged above; the migration is Neon-ready (SSL handling +
    unpooled-for-DDL).
## Phase 2 — Backend skeleton + core services + REST — DONE (verified on local Postgres)
- **Branch/PR:** `phase-2-services-rest` (cut from `phase-1-data-model` HEAD, since Phase 1 is
  not yet merged to `main`; committed locally, push + PR pending human go-ahead).
- **Scope:**
  - **`services/`** (framework-free, typed, `db`+`user_id` in, `ServiceError` out) for
    `users` (dev stub + `/me`), `exercises` (list/filter/get/create-custom), `sessions`
    (CRUD + detail-with-sets), `sets` (**PR detection**), `prs` (list/history), `skills`
    (overview/detail/upsert), `analytics` (volume/frequency), and `health` (DB ping).
  - **PR detection** is a single **chronological recompute** over a user's sets for an
    exercise, shared by log/update/delete so they can never drift; it reproduces the legacy
    detection priority (hold → weight → reps → first_log) keyed on `exercise_id`.
  - **REST routers** mirroring the `03` surface table 1:1 (15 paths incl. `/api/health`,
    `/api/me`), thin adapters only. **DI** (`api/deps.py`): `get_db` (commit/rollback/close),
    `pagination` (limit≤100), and a **stubbed `current_user`** that auto-provisions a fixed
    dev user so writes work before real auth (Phase 3 swaps in session/bearer resolution).
  - **`core/errors.py`** (`ServiceError` → `{not_found:404, forbidden:403, conflict:409,
    validation:422}`, canonical `{"error":{kind,message,details?}}` envelope, generic-500
    guard), **`core/logging.py`** (JSON logs + request-id contextvar + `X-Request-ID`
    middleware), **`core/slugs.py`**. Pydantic v2 schemas for all I/O; same-site CORS.
  - `core/config.py` extended (defaulted `web_origin`/`cors_extra_origins`/`log_level`; DB
    URLs stay the only required vars so the auth-stubbed app boots without the Phase 3+ env).
- **DoD evidence:**
  - **`pnpm exec turbo run build lint typecheck test` → 7/7 successful** (web
    build+lint+typecheck cached; api build+lint+typecheck+**test**). API `ruff` + `black
    --check` + `mypy` (strict, 69 files) clean.
  - **`uv run pytest -q` → 70 passed.** Highlights: **8 PR-detection unit tests** (first_log,
    weight→reps progression, hold_time, the weight-needs-reps legacy quirk, update/delete
    recompute, measurement + ownership guards); **router tests** for exercises/sessions/sets/
    prs/analytics/skills/me driving the real HTTP surface through the stub user (full
    log-a-workout loop, PR celebration payload, pagination, 404/409/422 envelopes,
    `X-Request-ID`); service tests for visibility scoping, analytics math, skills upsert; and
    an **architecture guard** (`test_architecture.py`) grepping routers for any DB/query
    access — enforcing "no logic outside `services/`".
  - **`GET /api/health`** performs a real `SELECT 1` (via `services/health.ping`) and returns
    `{"status":"ok","db":"ok"}`; **`app.openapi()`** generates cleanly (15 paths).
- **Notes / decisions:**
  - **PR contract ported faithfully from legacy** (kept, not re-litigated): weight PRs require
    *both* weight and reps recorded, so a heavier weight-only set is not a weight PR — flagged
    here as a candidate for a future product review, not changed now. `personal_records
    .achieved_at` now uses the **session's `performed_at`** (when it happened) rather than the
    legacy insert-time `now()`.
  - **`current_user` auto-provisions the dev user** (`dev@tempo.local`) idempotently — this
    is a Phase-2-only shortcut so features work before Phase 3 auth; the `CurrentUser`
    interface is stable so routers won't change when real auth lands.
  - **turbo strict-env fix:** added `passThroughEnv: ["TEST_DATABASE_URL"]` to the `test` task
    so the (throwaway) test-DB URL reaches pytest through `turbo run` on dev machines; CI is
    unaffected (its `postgres/postgres` default already matched the harness fallback).
  - New env: `CORS_EXTRA_ORIGINS`, `LOG_LEVEL` (both optional) added to `.env.example`. No
    Decision-Log change — Phase 2 implements D2/D3/D11, it doesn't alter them.
## Phase 3 — Identity + OAuth 2.1 AS 🔒 — NOT STARTED
## Phase 4 — Catalog import + illustration pipeline — NOT STARTED
## Phase 5 — MCP server (Python) + connector verification — NOT STARTED
## Phase 6 — Slice: Design system + app shell + Library — NOT STARTED
## Phase 7 — Slice: Log a workout (UI + MCP parity) — NOT STARTED
## Phase 8 — Slice: Dashboard + Skills module — NOT STARTED
## Phase 9 — Flagship polish pass — NOT STARTED
## Phase 10 — Deploy & launch — NOT STARTED
