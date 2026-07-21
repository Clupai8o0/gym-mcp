# Tempo — project context (read first)

**Tempo** is a personal-first, share-ready workout app: an illustrated full-gym **exercise
library**, fast **workout logging**, and a **progress dashboard**, all backed by one Python
service that is *also* exposed as an **MCP server** so a chat client (Claude/ChatGPT) can read
and update training over an OAuth connection.

## Status: planning complete, rebuild not yet started
- **The full plan lives in [`docs/`](./docs/) and is the source of truth.** Start with
  [`docs/README.md`](./docs/README.md), then [`docs/10-execution-plan.md`](./docs/10-execution-plan.md)
  (the phased roadmap) and [`docs/11-agent-workflow.md`](./docs/11-agent-workflow.md) (how to execute).
- Once Phase 0 runs, **`docs/STATUS.md` is the live state tracker** — read it to see where we are.
- ⚠️ The root `README.md` and the `api/`, `lib/`, `supabase/` dirs are the **OLD** TypeScript
  MCP app on Supabase. It is being **replaced** by a monorepo rescaffold (greenfield Neon; old
  Supabase archived read-only). Don't extend the old code — follow the docs.

## Locked decisions (don't silently re-litigate; changes go in the `01` Decision Log)
| | |
|---|---|
| Scope | Personal-first, **share-ready** (real accounts + OAuth; no billing/teams yet) |
| UI | One unified app: **library + logging + dashboard** |
| Catalog | **General gym**, ~800+ exercises from **free-exercise-db** (Unlicense) |
| Backend | **"One Python brain"** — FastAPI `services/` shared by REST **and** the MCP server |
| Images | Batch seed + on-demand fallback; **minimal monochrome line-art**; model **GPT Image 2** |
| Auth | **Hand-rolled OAuth 2.1 AS** in FastAPI; end-user login **delegated to Google OIDC** |
| Data | **Greenfield Neon**; Supabase archived read-only |
| Design | **Flagship polish** — x.ai design system (`npx getdesign@latest add x.ai`), motion as first-class |
| Sequencing | **Hybrid** — foundation phases (0–5) then vertical slices (6–8), polish (9), launch (10) |
| Skills | Calisthenics skill-tree kept as a **secondary module** |

## Stack & domains
- **Monorepo:** pnpm + Turborepo; Python via **uv**.
- **web** (Next.js App Router) → **`tempo.clupai.com`**
- **api** (FastAPI, Python 3.13, Vercel Fluid Compute) → **`api.tempo.clupai.com`** — serves
  REST + `/mcp` + `/oauth/*` + `/.well-known/*`. OAuth issuer = `https://api.tempo.clupai.com`.
- **DB:** Neon (SQLAlchemy 2.0 async + Alembic). **Blob:** Vercel Blob (illustrations).
- Two subdomains share `clupai.com` → **same-site**: session cookie `Domain=tempo.clupai.com`
  reaches both; browser→api calls use CORS + credentials + an `X-Tempo-Client` CSRF header.

## Execution model
- **Orchestrator:** Claude Opus (owns the plan, assigns phases, enforces gates).
- **Executor:** Codex + subagents (one phase = one branch = one PR, with acceptance criteria).
- **Frontend review gate:** Antigravity CLI on UI phases (6–9), against `docs/08` rubric.
- **Security review gate:** a **human** must sign off **Phase 3 (OAuth)** — no automated substitute.

## Hard guardrails (apply to every change)
- **Keep REST and MCP in lockstep** — both call the same `services/` function; a contract test enforces it.
- **No business logic outside `services/`.** Routers and MCP tools are thin adapters.
- **Security is non-negotiable in Phase 3:** PKCE S256, hashed tokens at rest, refresh rotation
  with reuse detection, exact redirect-URI match, resource/audience binding. See `docs/05`.
- **Never hand-roll password auth** — user identity is Google OIDC.
- **No batch image/seed jobs on Vercel** (300s limit) — they are offline scripts in `scripts/`.
- **Idempotent** seeds/migrations; correct **pooled vs unpooled** Neon URLs (app vs migrations).
- **Tokens-only styling** + the motion rulebook on UI (`docs/08`).
- **No non-goals** (teams, billing, social, nutrition). Flag scope creep and stop.
- **No secrets in the repo**; keep `.env.example` current.

## Conventions
Python: ruff + black + mypy, async everywhere. TS: eslint + prettier, strict, no `any` at the
API boundary (generate types from OpenAPI). Conventional Commits; one PR per phase with the
acceptance checklist ticked. Full detail in [`docs/12-conventions.md`](./docs/12-conventions.md).
