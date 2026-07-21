# 12 — Conventions

Shared standards so any agent's output looks like one author wrote it. Where a tool's default
is sane, we take it; deviations are listed.

## Repo & tooling

- **Monorepo:** pnpm workspaces + **Turborepo**. Root scripts run via `turbo` (`build`, `lint`,
  `typecheck`, `test`). Cache-friendly; only affected projects rebuild.
- **Python:** managed with **uv**. Target **Python 3.13**. One `pyproject.toml` per Python
  package; `uv.lock` committed.
- **Node:** pin the version in `.nvmrc`/`package.json` engines; pnpm as the only package manager
  (no npm/yarn lockfiles).
- **Secrets:** never in the repo. Local `.env` (gitignored); Vercel env for deployed. Keep
  `.env.example` exhaustive and value-less.

## Python (backend + scripts)

- **Style/lint:** `ruff` (lint + import sort) + `black` (format). `mypy` in strict-ish mode.
- **Async everywhere** in the API; async SQLAlchemy sessions; never block the event loop.
- **Structure:** logic in `services/` (no framework imports); routers/tools are thin. Pydantic
  v2 for all I/O schemas; `pydantic-settings` for config.
- **Errors:** raise typed `ServiceError`; map centrally (`core/errors.py`). Never leak internals.
- **Naming:** modules/functions `snake_case`; classes `PascalCase`; constants `UPPER_SNAKE`.
- **DB:** access only through services; explicit eager-loading (`selectinload`), no lazy loads
  across awaits; migrations only via Alembic (never `create_all` in app code).
- **Logging:** structured, with a request id; **never log secrets/tokens** (log hash prefixes).

## TypeScript / React (frontend)

- **Style/lint:** `eslint` (shared config in `packages/eslint-config`) + `prettier`. `tsc`
  strict; **no `any`** at the API boundary (use the generated OpenAPI types).
- **Components:** Server Components by default; `"use client"` only when interaction/motion needs
  it. Co-locate component + styles + tests.
- **Styling:** **tokens only** (from `08`) — no hardcoded color/space/duration/px. Motion via the
  shared `components/motion/` primitives + motion tokens.
- **Data:** typed `lib/api.ts` client; reads server-side where possible; mutations optimistic
  where specified. Regenerate the API types in CI; fail on drift.
- **Naming:** components `PascalCase`; hooks `useCamelCase`; files match the default export.
- **a11y:** every interactive element keyboard-usable, labeled, focus-visible; honor
  `prefers-reduced-motion`.

## Testing

| Layer | Tool | What to test |
|---|---|---|
| Services (Python) | `pytest` + async | Domain rules: PR detection, ownership checks, analytics math. The bulk of tests live here. |
| Routers (Python) | `pytest` + `httpx.AsyncClient` | Status codes, auth boundary, pagination, error mapping. |
| MCP contract | `pytest` | Each tool calls the same service and returns data equivalent to its REST sibling (**anti-drift**). |
| OAuth e2e | `pytest` | discovery→register→authorize→token→refresh→reuse-revocation (Phase 3 DoD). |
| Web unit | Vitest/RTL | Component states, formatting (kg/lb), optimistic update logic. |
| Perf/a11y | Lighthouse/axe on preview | CWV budgets (LCP<2.5s, CLS<0.1, INP<200ms), contrast, roles. |

- Tests run against a **Neon test branch** or local Postgres — never prod.
- A phase's new behavior ships with tests at the right layer; no merging red.

## Git & PRs

- **Branches:** `phase-<n>-<slug>` (execution phases); `fix/…`, `chore/…` otherwise. Never
  commit straight to `main`.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`).
  Small, logically-scoped commits.
- **PRs:** one per phase; description carries the acceptance-criteria checklist (ticked, with
  evidence) + gate results. Phase 3 embeds the security checklist + human sign-off; UI PRs embed
  the Antigravity rubric result.
- **Migrations** reviewed explicitly; destructive ones need a two-phase (deprecate→remove) plan.
- Co-author agent commits per the repo's commit-trailer convention.

## API & data conventions

- **IDs:** UUIDs everywhere in public contracts.
- **Units:** store **kg** and **seconds**; convert for display only.
- **Time:** `timestamptz`, ISO 8601 in JSON, UTC canonical.
- **Pagination:** `limit`/`offset`; default 50, max 100; list endpoints are user-scoped.
- **Errors (REST):** `{ "error": { "kind", "message", "details?" } }` with the mapped status.
- **Versioning:** additive changes preferred; breaking a public contract requires updating both
  REST and MCP + the generated types + a Decision-Log note.

## Documentation

- These `docs/` are authoritative. If code and a doc disagree, **fix one and note it** — don't
  leave them inconsistent. Architectural changes get a dated **Decision Log** entry in `01`.
- Keep `STATUS.md` current (per `11`). Keep `tempo://guide` (MCP resource) in sync with the tool
  list. Keep `.env.example` in sync with real env usage.

## Definitions of "don't"

- Don't put logic in routers/tools. Don't hardcode styles. Don't log secrets. Don't run batch
  image/seed jobs on Vercel. Don't add non-goal features. Don't hand-roll password auth. Don't
  merge red or skip a required gate. Don't migrate destructively without a plan.
