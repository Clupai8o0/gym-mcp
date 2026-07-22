# 01 — Architecture

## System shape

```
                          ┌─────────────────────────────────────────────┐
   Browser  ───────────▶  │  Vercel project: web  (Next.js, App Router)  │
                          │  tempo.clupai.com                            │
                          │  - UI: /library /log /dashboard /settings    │
                          │  (browser fetches data from api.* via CORS)  │
                          └───────────────┬─────────────────────────────┘
                                          │  server-side fetch / browser CORS
                                          ▼
   claude.ai / ChatGPT ──▶  ┌─────────────────────────────────────────────┐
   (MCP client, OAuth)      │  Vercel project: api  (FastAPI, Fluid Compute)│
                            │  api.tempo.clupai.com                        │
                            │   ┌──────────────┐   ┌──────────────────┐    │
   REST  ───────────────▶   │   │ api/routers/ │   │  mcp/  (MCP srv) │    │
                            │   └──────┬───────┘   └────────┬─────────┘    │
   MCP (Streamable HTTP)─▶  │          │                    │              │
                            │          ▼                    ▼              │
   OAuth 2.1 AS ─────────▶  │      ┌────────────────────────────┐          │
   /.well-known/*           │      │   services/ (THE BRAIN)    │          │
   /oauth/*                 │      │  sessions sets prs skills  │          │
                            │      │  exercises analytics       │          │
                            │      └──────────────┬─────────────┘          │
                            │   ┌─────────┐       │      ┌──────────────┐  │
                            │   │ oauth/  │       │      │ auth/ (Google│  │
                            │   │  AS     │       │      │  OIDC login) │  │
                            │   └─────────┘       ▼      └──────────────┘  │
                            └──────────────┬──────────────────────────────┘
                                           ▼
                    ┌──────────────┐   ┌──────────────┐   ┌───────────────┐
                    │ Neon Postgres│   │ Vercel Blob  │   │ OpenAI Images │
                    │ (SQLAlchemy) │   │ (illustr.)   │   │ (GPT Image 2) │
                    └──────────────┘   └──────────────┘   └───────────────┘

  Offline (not on Vercel): scripts/seed_catalog.py, scripts/generate_illustrations.py
```

**The load-bearing idea:** every capability lives once, in `services/`. REST handlers, MCP
tools, and the OAuth-protected endpoints are all thin adapters that call the same service
functions. This is what "one Python brain" means in practice.

## Monorepo layout

```
tempo/
├── apps/
│   ├── web/                     # Next.js (App Router). See 07-frontend-nextjs.md
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   ├── design/              # tokens + motion primitives (08-design-motion-system.md)
│   │   ├── vercel.ts            # headers/CSP for the web project
│   │   └── package.json
│   └── api/                     # FastAPI. See 03-backend-fastapi.md
│       ├── app/
│       │   ├── main.py          # builds the FastAPI app, mounts routers + MCP
│       │   ├── core/            # config, db, security, logging
│       │   ├── models/          # SQLAlchemy models
│       │   ├── schemas/         # Pydantic models
│       │   ├── services/        # ← business logic (shared by REST + MCP)
│       │   ├── api/routers/     # REST endpoints (thin)
│       │   ├── mcp/             # MCP server (Python SDK) → services
│       │   ├── oauth/           # OAuth 2.1 AS: metadata, DCR, authorize, token
│       │   └── auth/            # Google OIDC login + web sessions
│       ├── migrations/          # Alembic
│       ├── index.py             # Vercel entrypoint: exposes `app`
│       ├── pyproject.toml       # uv-managed
│       └── vercel.ts / vercel.json
├── packages/
│   ├── ui/                      # optional shared React components (x.ai wrappers)
│   ├── tsconfig/                # shared TS config
│   └── eslint-config/           # shared lint config
├── scripts/                     # offline jobs (Python; run locally / CI, NOT on Vercel)
│   ├── seed_catalog.py          # free-exercise-db → Neon
│   └── generate_illustrations.py# GPT Image 2 → Vercel Blob → exercises.illustration_url
├── docs/                        # you are here
├── pnpm-workspace.yaml
├── turbo.json
├── package.json                 # root; scripts orchestrate via turbo
└── .env.example
```

> **Why two Vercel projects on subdomains?** Next.js owns its own `/api` routes, which collides
> with mounting a full FastAPI ASGI app there. Deploying `web` (`tempo.clupai.com`) and `api`
> (`api.tempo.clupai.com`) as **separate Vercel projects from the same repo** keeps each
> framework native and independently deployable. The two subdomains share the registrable
> domain `clupai.com`, so they are **same-site**: a session cookie scoped to
> `Domain=tempo.clupai.com` reaches both, and the MCP resource + OAuth AS sit together on a
> single origin (`api.tempo.clupai.com`) — the simplest shape for the spec. The browser's API
> calls are cross-**origin**, so the API runs a small CORS allowlist. See
> `09-deployment-vercel.md` for CORS, cookie, and CSRF details.

## Component responsibilities

| Component | Owns | Never does |
|---|---|---|
| `web` (Next.js) | Rendering, client interaction, motion, calling the API with the session cookie | Business logic, DB access, holding secrets beyond public config |
| `api/services/` | **All** domain logic, all DB reads/writes, PR detection, validation | Knowing whether its caller is REST or MCP |
| `api/api/routers/` | HTTP request/response shape, status codes, pagination | Domain rules (delegates to services) |
| `api/mcp/` | MCP tool definitions, mapping tool args → service calls | Duplicating any logic that lives in services |
| `api/oauth/` | OAuth 2.1 AS endpoints, PKCE, token issuance/rotation | User authentication (delegates to Google via `auth/`) |
| `api/auth/` | Google OIDC login, web session cookies | Issuing MCP/OAuth tokens |
| Neon | Durable state | — |
| Vercel Blob | Illustration binaries | — |
| `scripts/` | Offline catalog import + batch image gen | Running inside a request handler |

## Request paths (concrete)

- **Web read** (e.g. library list): a React Server Component fetches
  `api.tempo.clupai.com/api/exercises` server-side (forwarding the session cookie) →
  FastAPI router → `services.exercises.list()` → Neon. Browser mutations call the same host via
  CORS with credentials.
- **Web login:** Browser → `api.tempo.clupai.com/oauth/login/google` → FastAPI `auth/` → Google
  OIDC → callback → set `Domain=tempo.clupai.com`, httpOnly session cookie → redirect to
  `tempo.clupai.com`.
- **MCP tool call:** claude.ai (holding a Tempo access token) → `api.tempo.clupai.com/mcp` →
  FastAPI MCP app → bearer token resolved to `user_id` → `services.sets.log()` → Neon.
- **MCP connect (first time):** claude.ai fetches
  `api.tempo.clupai.com/.well-known/oauth-protected-resource` → discovers AS → registers via DCR
  → redirects user to `/oauth/authorize` → user logs in via Google → AS issues code → claude.ai
  exchanges code (PKCE) at `/oauth/token` → gets tokens.
- **On-demand illustration:** Browser opens an exercise with no image → API enqueues/produces
  a single GPT Image 2 render → uploads to Blob → sets `illustration_url` → returns it.

## Technology choices & rationale (Decision Log)

Append-only. If a phase changes one of these, add a dated entry; don't edit history.

| # | Decision | Rationale | Alternatives rejected |
|---|---|---|---|
| D1 | **Neon** Postgres | Serverless-native, branchable (per-preview DB), generous free tier, standard Postgres so SQLAlchemy/Alembic "just work" | Supabase (leaving it), Vercel Postgres (discontinued) |
| D2 | **FastAPI** as the one backend | Python, async, great DX, first-class on Vercel Fluid Compute; lets REST+MCP share a service layer | Keeping TS MCP (logic drift), Node backend (user wants Python) |
| D3 | **SQLAlchemy 2.0 async + Alembic** | Mature ORM + migrations; async fits serverless; explicit models | Raw asyncpg (more boilerplate), Prisma-py (immature) |
| D4 | **Python MCP SDK**, mounted in FastAPI | Same process as services → zero-latency reuse of the brain | Separate MCP proxy (extra hop), keeping TS MCP |
| D5 | **Hand-rolled OAuth 2.1 AS**, Google OIDC for users | User's explicit choice; delegating user auth to Google removes password risk while satisfying "hand-rolled OAuth" | Managed provider (WorkOS/Stytch/Clerk) — declined by user |
| D6 | **Two Vercel projects on subdomains** (`tempo.clupai.com` + `api.tempo.clupai.com`) | Native Next.js + native FastAPI; same-site parent-domain cookie reaches both; MCP resource + AS share one clean origin | Single project (framework collision); same-origin **proxy rewrites** (extra hop, muddier OAuth issuer) |
| D7 | **Batch seed + on-demand fallback** for images | Complete library up front, graceful handling of new/custom exercises | Fully on-demand (patchy library), batch-only (custom exercises get no art) |
| D8 | **GPT Image 2** | Current flagship; `gpt-image-1` retires 2026-10-23 so we must not build on it | gpt-image-1 (deprecating), 1.5/Mini (fine, but user chose 2) |
| D9 | **Minimal monochrome line-art** style | Consistent at ~1000 images, tiny + legible, matches x.ai aesthetic | Flat vector / silhouette (less on-brand) |
| D10 | **pnpm + Turborepo + uv** | Standard, fast, cache-friendly monorepo tooling across TS + Python | Nx (heavier), Poetry (uv is faster), npm workspaces (slower) |
| D11 | **exercise_sets → exercise_id FK** (not free-text names) | Links every set to catalog metadata + illustration; enables real analytics | Free-text names (current app's weakness) |
| D12 | **Vercel Blob** for images | Native, CDN-backed, public URLs, no S3 setup | S3/R2 (more setup for no gain here) |
| D13 (2026-07-22, Phase 3) | **Stateless signed web-session cookie** (no `web_sessions` table) | `02` left this open; a compact HMAC-signed httpOnly cookie (sliding renewal) needs no DB round-trip and fits Fluid Compute's statelessness | Server-side session table (extra write/read per request, no benefit at this scale) |
| D14 (2026-07-22, Phase 3) | **Token hashing = HMAC-SHA256 keyed by `TOKEN_HASH_PEPPER`** (not bare SHA-256) | A DB leak alone (without the server-side pepper) can't confirm a stolen/guessed token; the pepper env var was already anticipated in `.env.example` | Bare SHA-256 (weaker if the token store leaks), bcrypt/argon2 (needless — tokens are already 256-bit random) |
| D15 (2026-07-22, Phase 3) | **Consent shown every authorize + recorded via structured log** (no `oauth_consents` table) | Satisfies "shown & recorded, ≥once per client" without new schema; re-consent per connect is more privacy-preserving for a personal app | Persisted consent table (skippable re-consent; more state for no user benefit yet) |
| D16 (2026-07-22, Phase 3) | **Two additive token columns beyond `02`'s DDL:** `resource` on access+refresh tokens; `chain_id` on refresh tokens | `resource` makes the mandatory audience-binding check (`05` B5) a real per-token comparison; `chain_id` lets reuse-detection revoke the whole rotation lineage in one indexed write (`05` B4). Both additive/non-destructive | Global single-resource assumption (weaker audience binding); recursive-CTE walk of `rotated_from` (more error-prone for the security-critical revoke path) |
| D17 (2026-07-22, Phase 3) | **`authlib` for Google ID-token (JWS/JWKS) verification**; opaque tokens via `secrets`, hashing via `hashlib`/`hmac` | `05` recommends not reinventing JOSE crypto while keeping the AS endpoints explicit and auditable | `python-jose` (less maintained), hand-rolled RS256/JWKS (crypto risk) |

## Cross-cutting principles

- **Stateless request handling.** Fluid Compute reuses instances, but never rely on in-memory
  state between requests. All state is in Neon/Blob.
- **Async everywhere in the API.** Async SQLAlchemy sessions; never block the event loop.
- **Connection pooling:** use Neon's **pooled** connection string (PgBouncer) for the app;
  use the **direct** (unpooled) string only for Alembic migrations. See `09`.
- **Validation at the edge, rules in the middle.** Pydantic validates shape at routers/tools;
  services enforce domain invariants (e.g., PR detection).
- **Idempotent seeds.** `seed_catalog.py` and `generate_illustrations.py` must be safe to
  re-run; they upsert by a stable `source_id`/slug and skip already-done work.
- **Everything an agent builds ships behind a Definition of Done** (tests + acceptance
  criteria in `10-execution-plan.md`).
