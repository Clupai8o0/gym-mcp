# Tempo — Planning & Build Docs

> **Tempo** is a personal-first, share-ready workout app: a beautifully illustrated
> full-gym **exercise library**, fast **workout logging**, and a **progress dashboard** —
> all backed by one Python service that is *also* exposed as an **MCP server** so a chat
> client (Claude/ChatGPT) can read and update your training over an OAuth connection.

This folder is the **single source of truth** for rebuilding the app. It is written to be
executed by autonomous coding agents, phase by phase, with minimal human intervention.

---

## How to use these docs

**If you are a human:** read `00-overview.md` → `01-architecture.md` → `10-execution-plan.md`.
Everything else is reference the agents pull in per phase.

**If you are an executing agent:** your entry points are **`10-execution-plan.md`**
(what to build, in what order, with acceptance criteria) and **`11-agent-workflow.md`**
(how to pick up a phase, the review gates, and the definition-of-done protocol).
Do not start coding until you have read both, plus the reference docs your phase names.

---

## Document index

| # | Doc | Read it when you need… |
|---|-----|------------------------|
| 00 | [`00-overview.md`](./00-overview.md) | The product vision, users, scope, non-goals, glossary |
| 01 | [`01-architecture.md`](./01-architecture.md) | The system shape, monorepo layout, and **why** each decision was made |
| 02 | [`02-data-model.md`](./02-data-model.md) | The Neon schema, every table, and the migration strategy |
| 03 | [`03-backend-fastapi.md`](./03-backend-fastapi.md) | How the FastAPI service layer & REST API are structured |
| 04 | [`04-mcp-server.md`](./04-mcp-server.md) | How the Python MCP server reuses the service layer |
| 05 | [`05-auth-oauth.md`](./05-auth-oauth.md) | The hand-rolled OAuth 2.1 server + Google login (**security-critical**) |
| 06 | [`06-catalog-and-images.md`](./06-catalog-and-images.md) | Seeding the catalog and generating the ~1000 illustrations |
| 07 | [`07-frontend-nextjs.md`](./07-frontend-nextjs.md) | The Next.js app: the three surfaces, routing, data fetching, PWA |
| 08 | [`08-design-motion-system.md`](./08-design-motion-system.md) | The x.ai design system, tokens, and the motion rulebook |
| 09 | [`09-deployment-vercel.md`](./09-deployment-vercel.md) | Deploying web + api to Vercel, envs, Neon pooling, Blob |
| 10 | [`10-execution-plan.md`](./10-execution-plan.md) | **The phased roadmap** — the master checklist |
| 11 | [`11-agent-workflow.md`](./11-agent-workflow.md) | Orchestrator/Codex/Antigravity roles & review gates |
| 12 | [`12-conventions.md`](./12-conventions.md) | Code style, testing, commits, folder rules |
| 13 | [`13-performance.md`](./13-performance.md) | Measured load-time audit + the ranked fix plan |

---

## The decisions this plan is built on

These were settled during planning. Do **not** silently re-litigate them; if a phase
forces a change, record it in the Decision Log in `01-architecture.md`.

| Decision | Choice |
|---|---|
| **Product scope** | Personal-first, **share-ready** (real accounts + OAuth, but no billing/teams yet) |
| **UI purpose** | One unified app: **library + logging + progress dashboard** |
| **Catalog** | **General gym**, ~800+ exercises seeded from **free-exercise-db** (Unlicense) |
| **Backend** | **"One Python brain"** — FastAPI owns all logic; MCP is a thin layer over the same services |
| **Images** | **Batch seed + on-demand fallback**; **minimal line-art, monochrome**; model = **GPT Image 2** |
| **Auth** | **Hand-rolled OAuth 2.1 AS** in FastAPI; end-user login **delegated to Google OIDC** |
| **Data** | **Greenfield Neon**; old Supabase kept as a read-only archive |
| **Design bar** | **Flagship polish** — x.ai design system, motion as a first-class concern |
| **Sequencing** | **Hybrid** — foundation phases first, then vertical feature slices |
| **Skill tree** | Kept as a **secondary module** layered on the catalog |
| **Name** | **Tempo** — served at `tempo.clupai.com` / `api.tempo.clupai.com` |

---

## Stack at a glance

- **Monorepo:** pnpm workspaces + Turborepo. Python managed with **uv**.
- **Frontend:** Next.js (App Router, React Server Components) on Vercel.
- **Backend:** FastAPI (Python 3.13) on Vercel **Fluid Compute**, serving REST **+** MCP **+** the OAuth AS.
- **DB:** **Neon** Postgres via SQLAlchemy 2.0 (async) + Alembic migrations.
- **Storage:** Vercel Blob for exercise illustrations.
- **Auth:** OAuth 2.1 (hand-rolled AS) + Google OIDC for end-user identity.
- **Images:** OpenAI **GPT Image 2** (offline batch seed job + on-demand endpoint).
- **Deploy:** Two Vercel projects from one repo — `web` (`tempo.clupai.com`) + `api` (`api.tempo.clupai.com`), same-site subdomains (parent-domain cookie + CORS).
