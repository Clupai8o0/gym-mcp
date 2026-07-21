# Tempo

Personal-first, share-ready workout app: an illustrated full-gym **exercise library**, fast
**workout logging**, and a **progress dashboard** — all backed by one Python service that is
_also_ exposed as an **MCP server**, so a chat client (Claude/ChatGPT) can read and update your
training over an OAuth connection.

> **Planning & build docs are the source of truth.** Start with
> [`docs/README.md`](./docs/README.md) → [`docs/10-execution-plan.md`](./docs/10-execution-plan.md)
> (the phased roadmap) → [`docs/STATUS.md`](./docs/STATUS.md) (live state).

## Monorepo layout

```
tempo/
├── apps/
│   ├── web/          # Next.js (App Router) → tempo.clupai.com
│   └── api/          # FastAPI (Python 3.13, uv) → api.tempo.clupai.com  (REST + /mcp + /oauth/*)
├── packages/
│   ├── tsconfig/     # shared TypeScript config
│   └── eslint-config/# shared ESLint (flat) config
├── scripts/          # offline Python jobs (seed / images) — never on Vercel
├── docs/             # the plan (authoritative)
└── legacy/           # archived old TS/Supabase app (read-only)
```

The load-bearing rule: **every capability lives once, in `apps/api/app/services`**. REST routers,
MCP tools, and OAuth endpoints are thin adapters over the same service functions
("one Python brain"). See [`docs/01-architecture.md`](./docs/01-architecture.md).

## Toolchain

- **Node** ≥ 20 (repo pins 24 via `.nvmrc`), **pnpm** 11, **Turborepo** — JS/TS + task runner.
- **Python** 3.13 via **uv** — the API and offline scripts.

## Quickstart

```bash
# 1. Node/TS workspaces
pnpm install

# 2. Python (API) deps
cd apps/api && uv sync && cd ../..

# 3. Environment
cp .env.example .env   # fill in as phases require (nothing needed to boot Phase 0)
```

Run everything (build + lint + typecheck + test across the monorepo):

```bash
pnpm exec turbo run build lint typecheck test
```

Run each app locally:

```bash
pnpm --filter @tempo/web dev                    # web → http://localhost:3000
pnpm --filter @tempo/api dev                    # api → http://localhost:8000
curl localhost:8000/api/health                  # -> {"status":"ok"}
```

## Contributing

One phase = one branch (`phase-<n>-<slug>`) = one PR. Conventional Commits.
See [`CONTRIBUTING.md`](./CONTRIBUTING.md) and [`docs/12-conventions.md`](./docs/12-conventions.md).
