# STATUS — live state tracker

The orchestrator's source of truth for "where are we" (see
[`11-agent-workflow.md`](./11-agent-workflow.md)). One section per phase; update at the end of
each phase with what shipped, DoD evidence, and any decisions.

**Legend:** `NOT STARTED` · `IN PROGRESS` · `BLOCKED` · `DONE`

---

## External prerequisites (needed before later phases)

Not required for Phase 0. Track here so they don't become surprise blockers:

- [ ] Neon project (primary + preview branch); pooled + unpooled URLs — **Phase 1**
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

## Phase 1 — Neon + data model — NOT STARTED
## Phase 2 — Backend skeleton + core services + REST — NOT STARTED
## Phase 3 — Identity + OAuth 2.1 AS 🔒 — NOT STARTED
## Phase 4 — Catalog import + illustration pipeline — NOT STARTED
## Phase 5 — MCP server (Python) + connector verification — NOT STARTED
## Phase 6 — Slice: Design system + app shell + Library — NOT STARTED
## Phase 7 — Slice: Log a workout (UI + MCP parity) — NOT STARTED
## Phase 8 — Slice: Dashboard + Skills module — NOT STARTED
## Phase 9 — Flagship polish pass — NOT STARTED
## Phase 10 — Deploy & launch — NOT STARTED
