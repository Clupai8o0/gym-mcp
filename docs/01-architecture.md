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
| D18 (2026-07-22, Phase 4) | **free-exercise-db pinned at commit `b0eed06`** (873 exercises, 2026-05-24) in `app/catalog/dataset.py` | Reproducible seed (`06` DoD): a fetch resolves to identical bytes every run; the seed validates enum values against the `exercises` CHECKs and reports drift instead of failing mid-transaction | Tracking `main` (non-reproducible), vendoring the 1 MB JSON into the repo (stale, bloats history) |
| D19 (2026-07-22, Phase 4) | **New `unavailable` (503) `ErrorKind`** for a failed image provider/Blob upstream | The on-demand endpoint needs an honest "dependency down, retry later" distinct from a 500 bug or a 4xx client error; additive to the envelope, no existing shape changed | Reusing 500 (hides a transient upstream as an internal bug), a 4xx kind (misattributes the failure to the client) |
| D20 (2026-07-22, Phase 4) | **`scripts/` is its own `uv` project** importing `apps/api` via a `sys.path` shim; the offline jobs call the same `services/` as REST/MCP | "One Python brain" — the batch seed/image logic is the same code the runtime uses (`generate_and_store` is shared by the batch job and the on-demand endpoint), not a parallel copy | A duplicate seed/image implementation in `scripts/` (drift), installing `apps/api` as a package (it is a build-system-less virtual project) |
| D21 (2026-07-22, Phase 5) | **MCP mounted as a Starlette `Route("/mcp")` behind a custom bearer-auth ASGI wrapper**, not the SDK's built-in OAuth. The wrapper reuses `services/oauth.resolve_access_token` (REST's auth path) and binds the principal via a contextvar (`app/mcp/runtime`); tools open their own session via `core/db.session_scope` | A `Route` serves the exact `/mcp` with no trailing-slash redirect (a `Mount` 307-redirects `/mcp`→`/mcp/`); reusing our resolver keeps **one** auth path and is independent of the SDK's evolving auth API; contextvar + `session_scope` keep tools as pure "call a service" shims (the architecture guard forbids DB access in `app/mcp`) | `app.mount()` the SDK app (double `/mcp` path + redirect), the SDK's `TokenVerifier`/`AuthSettings` machinery (second auth path, version-brittle), threading `db`/principal through every tool (can't — tools aren't FastAPI-DI) |
| D22 (2026-07-22, Phase 5) | **Stateless Streamable-HTTP with `json_response=True`**; DNS-rebinding **Host/Origin allowlist kept on**, derived from settings (public host + localhost + `MCP_ALLOWED_HOSTS`) | Stateless + JSON is exactly how claude.ai talks to a remote server and is trivial to reason about server-side; keeping the SDK's Host check on is defense-in-depth behind the OAuth bearer, with a config knob so previews/hosts stay flexible | SSE-streaming responses (needless session state for request/response tools), disabling the Host check (drops a free layer) |
| D23 (2026-07-22, Phase 5) | **Exercise chat-identity rule = `services/exercises.resolve_ref`** (UUID → exact slug → exact case-insensitive name; global beats custom; a genuine top-tier tie returns candidates). MCP `get_exercise`/`log_set`/`get_prs`/`get_pr_history` accept a free-form `exercise` | `04` deferred the exact rule to Phase 5: chat users say names, not UUIDs, so resolution must live in a service (not the adapter) and be deterministic + safe (never silently pick between two real movements) | Only accepting UUIDs (round-trip-heavy in chat), fuzzy/`ILIKE` name matching (ambiguous, surprising), resolving inside the tool (business logic in an adapter — banned) |
| D24 (2026-07-22, Phase 6) | **`getdesign x.ai` ships a `DESIGN.md` spec, not a component library** → the token layer (`design/tokens.css`) + `components/ui/` wrappers are authored from it. Reconciled two vendor/`08` conflicts: (a) `08` mandates a **theme-aware light variant** even though the x.ai spec is dark-only — dark stays the signature default (`:root`), light follows `prefers-color-scheme`; (b) styling is **CSS Modules + token vars** (not Tailwind) to make "tokens-only" objectively enforceable. Motion split: CSS for enters (`FadeIn`/`Stagger`), the `motion` lib for interruptible pieces (`Pressable`/`Sheet`), React `<ViewTransition>` for the list→detail morph | `08` explicitly says reconcile vendor vs doc and log deviations; the spec is guidance, the project docs win on the light-variant decision; CSS Modules keep every value a `var(--token)` (no utility-class escape hatch), which the Antigravity rubric checks | Treating `getdesign` as a code dep (it isn't one), dark-only (drops `08`'s theme-aware requirement), Tailwind (utility values blur the tokens-only line), a motion lib for everything (heavier, worse enter perf than GPU CSS) |
| D25 (2026-07-22, Phase 6) | **Additive REST `GET /api/exercises/by-slug/{slug}`** backed by new `services/exercises.get_by_slug` (exact slug, visibility-scoped, global-beats-custom) — the web Library addresses exercises by slug (`/library/{slug}`) but the existing detail GET is by UUID | Keeps slug→exercise resolution **in `services/`** (guardrail: no logic outside services), routed before the UUID `{exercise_id}` path so the literal wins; complements MCP's `resolve_ref` (same rule) without changing any existing endpoint or the MCP↔REST contract | Resolving slug in the router/frontend (business logic in an adapter — banned), reusing `resolve_ref` over a public REST verb (its name/UUID overloading + conflict-on-tie is chat-shaped, not REST-shaped), list-then-filter client-side (wasteful, leaks logic) |
| D26 (2026-07-22, Phase 7) | **Browser mutations use a separate client (`lib/client.ts`) — not Server Actions.** Set logging POSTs directly to the API from the browser (`credentials:'include'` + `X-Tempo-Client`), reusing the same `sessions`/`sets` endpoints REST/MCP already expose. **No new backend code** — Phase 5 already shipped every session/set surface + the MCP↔REST contract tests that prove chat parity | Logging must feel instant and work offline; an optimistic client call + IndexedDB queue is simpler and faster than round-tripping a Server Action through the web origin, and it keeps the API the single write path (so a set logged in the UI is byte-identical to one from chat, already contract-tested). REST/MCP lockstep needs **zero** change this phase | Server Actions (extra hop web→api, harder to make optimistic/offline), a new "active session" endpoint (the client treats today's most-recent session as active — no schema/contract change), duplicating write logic in the web app (drift) |
| D27 (2026-07-22, Phase 7) | **Offline-first logging = an app-managed IndexedDB write-queue** (`lib/offline`), flushed on the `online` event; the **service worker is minimal** (installable + offline app-shell only) and never touches the API origin | The DoD's "offline logging syncs on reconnect" is the high-value case; an app-level queue keyed by the optimistic row's client id is reliable and testable, and reconciles the server's PR verdict on sync. The `online` event is universally supported (Background Sync is not); keeping the SW off the API origin means authenticated data is never served stale from cache. **Install polish + icons are explicitly Phase 9** | Background Sync API (Safari/Firefox gaps), caching API responses in the SW (stale auth'd data), a heavier offline story for browsing/dashboard (out of scope — v1 offline is logging only) |
| D28 (2026-07-22, Phase 8) | **Additive exercise-art fields on `PrOut`** (`illustration_url`, `illustration_status`, `is_custom`) read from the exercise the PR already joins — so the Dashboard shows each record with its illustration | Keeps REST and MCP in lockstep automatically (both surfaces serialize `PrOut` via `from_pair`; the MCP↔REST contract test still asserts equality) and avoids an N+1 exercise fetch per PR in the web layer; purely additive (no existing field changed) | A separate "PRs-with-art" endpoint (drift from `get_prs`), fetching each exercise from the browser per PR (N+1, leaks joins to the client), denormalizing art onto `personal_records` (redundant, can go stale) |
| D29 (2026-07-22, Phase 8) | **Settings (units + Connected apps) are REST-only account-management, not MCP tools**, and **connected-apps revoke** is a new **user-scoped** `services/connections` over the OAuth tables (`GET /api/connections`, `DELETE /api/connections/{client_id}`) that only ever sets `revoked_at` on the **caller's own** access+refresh tokens | The `04` tool table is a fixed training surface (15 tools); display units + OAuth-grant management are web account concerns (docs/07 frames Settings as web-only), so adding MCP tools would be scope creep. Revoke reuses the exact `revoked_at` mechanism the AS reuse-detection path writes and changes **no** issuance/PKCE/rotation semantics — so **Phase 3's security sign-off is unaffected** (a self-service view of, and off-switch for, one's own grants) | An MCP `revoke_connection` tool (a client revoking its own transport mid-call — confusing, unasked-for), mutating tokens from the router (banned — logic lives in `services/`), a whole new grants table (the existing hashed-token tables already model the grant) |
| D30 (2026-07-23, Phase 9) | Three polish-pass balances: **(a)** a distinct `--input-border` token at a visible **3:1** (WCAG 1.4.11) for functional form controls (input/select/number pad) while decorative card/divider hairlines keep `--border`; **(b)** catalog reads stay `cache:"no-store"` (perf audit flagged them as cacheable) because `list/get exercises` responses include per-user **custom** rows; **(c)** the app-shell nav keeps its CSS snap indicator — **no `motion` `layoutId` sliding tab** — and `Pressable` was rewritten to pure CSS + `Sheet` `next/dynamic`-imported, so `motion` is out of the Library/Dashboard initial bundles | Phase 9's gate is the `08` rubric, which demands **both** AA a11y and the x.ai aesthetic; where they tension, functional controls win on contrast (they must be identifiable) but decoration stays hairline. Correctness beats a TTFB win — caching catalog cross-user would leak custom exercises. And a nicety (sliding tab) isn't worth reintroducing `motion` to every authed page's critical bundle | Bumping every border to 3:1 (breaks the hairline language on decoration), caching per-user catalog reads (data leak), a `motion`-driven nav indicator (undoes the bundle wins), leaving `--text-muted` at `#7d8187` (fails AA on elevated surfaces) |
| D31 (2026-07-31, Phase 11A) | **A session's lifecycle is `ended_at`, and dangling sessions are retired lazily on read — not on create.** `get_active_session` = "newest row with `ended_at IS NULL`"; before answering it finishes any open session untouched for **12 h**, stamping `ended_at` from that session's **last set** (its start if it has none). Starting a workout deliberately does **not** auto-finish a previous one, and `finish_session` is **idempotent** (a second finish is a no-op, not a 409) | The date heuristic it replaces evaluated in the *server's* timezone: training at 5 pm in UTC−8 was already "tomorrow" in UTC (no Continue card, duplicate session), and a workout finished at 7 am still read "In progress" at 11 pm. A read-time sweep needs no cron (there is none on Fluid Compute), and dating the close from the last set means an abandoned session's `duration_minutes` reflects the training, not the hours it sat open. Auto-finishing on create would make `log_session` — which chat also uses to **backfill** historical workouts — silently mutate unrelated rows | Auto-finish on create (surprising side effect on a backfill; still leaves a session dangling if the user never returns), a scheduled sweep (no scheduler), 409 on double-finish (breaks retry/offline safety), keeping the date heuristic (the bug) |
| D32 (2026-07-31, Phase 11B) | **The authenticated shell has no top bar.** One `TabBar` component renders as a bottom tab bar below 768px and the *same* nav as a left rail above it; `Log` is a **state** (accent + dot badge while a session is live), not just a destination; the docked `SessionBar` is suppressed on the session's own page. Separately, **all date/time formatting is hand-rolled** (no `Intl`) and takes an explicit UTC-or-local `Zone`, with a `LocalTime` component rendering **UTC server-side then local once hydrated** | The governing constraint is one phone screen with no scrolling: bottom-anchored nav sits in the thumb arc and buys back the ~56px a sticky header cost on every route, and two compositions of one component means mobile and desktop can't drift. On formatting: `toLocaleDateString(undefined, …)` threw a **live hydration error** on `/settings` and `/log/[id]` — Node and Chrome resolve different locales *and* format the same locale differently (`pm`/`PM`). Hand-rolled output removes the locale variable entirely; UTC-then-local removes the timezone one without ever rendering a blank or shifting layout | A second desktop nav component (drift), icon-only tabs (a memory test mid-set), pinning `Intl` to one locale (Node's and Chrome's ICU still disagree), `suppressHydrationWarning` alone (keeps the server's *wrong* text), blanking timestamps until mount (layout shift on metadata), sending the browser's timezone to the server (a round-trip and a fingerprinting surface for cosmetic text) |
| D33 (2026-07-31, Phase 11C) | **`/dashboard` is home and the front door**; the sections it used to stack live at `/progress/{volume,frequency,records,skills}` and render **inline in home's right column above 768px**. Home's stats window is a **rolling seven days**, not a calendar week, and the seven-day strip is bucketed **client-side**. The range control moves to `/progress/volume` + `/progress/frequency` (and rewrites the *current* path); `/progress/records` has none | One phone screen with no scrolling is the governing constraint, and three full-height charts can't share it — but the split is a mobile constraint, so desktop keeps everything on one page rather than growing a second navigation. A rolling window is defined by two instants and therefore means the same thing in every timezone, whereas "since Monday" would have to be resolved server-side in UTC (the exact trap D31 removed); a *calendar* strip can only be bucketed where the timezone is known, i.e. the browser. Records are all-time (`listPrs()` takes no window), so a control there was reading as broken | Keeping one long dashboard (four screens of scrolling on a phone), a mobile-only summary with desktop unchanged (two dashboards to maintain), computing "this week" in UTC (wrong for up to a day, every day), fetching the strip client-side (a second authenticated round-trip for six cells) |
| D34 (2026-07-31, Phase 11D) | **The service worker never caches an authenticated navigation.** Only `/` and `/offline` — which render no user data — are precached or runtime-cached; an offline hit on any other route falls through to `/offline`. Cache version bumped to `v3` so existing clients evict, and sign-out wipes all Cache Storage (`lib/pwa.clearAppCaches` + a `tempo:clear-caches` message to the worker) | Corrects the assumption recorded in **D27**: keeping the worker off the *API* origin protects API **responses**, but every authed page is server-rendered HTML that already contains the user's data, and v2 cached those per-URL. Reproduced: visit `/dashboard` signed in → sign out → go offline → the previous user's full dashboard renders from cache, name and records included, and nothing ever expired it. On a shared or family device that is one person's training data shown to the next | Caching authed HTML with a short TTL (a cache outlives a session cookie regardless), clearing on sign-out **only** (misses a crash, a cleared cookie, or a device that never signs out), dropping navigation caching entirely (loses the offline shell) |
| D35 (2026-07-31, Phase 11F) | **Home fills the desktop viewport instead of scrolling**, and the rail is **collapsible**. The shell marks the home route `[data-fill]`, takes `height: 100dvh`, and hands the page a fixed box it divides into five rows — the last one (`1fr`) holds Volume · Frequency · Records side by side, each scrolling **inside its own panel body**. Guarded to `≥1024px` **and** `≥720px` tall. Rail state is a **cookie**, read server-side, and `--rail-width` is the only thing the toggle changes. Two deliberate `docs/08 §4` exceptions: the rail's `width` and the content column's `padding-left` are animated | "One screen, no scrolling" was the phone constraint; on desktop the same idea means the dashboard is a dashboard — you see all of it, and only the panel under your cursor moves. Rows pair up (stats beside the strip, the two highlight rows side by side) because otherwise the panel row collapses to ~110px and the panels are present but useless. The cookie beats `localStorage` because the server can then stamp the width into the first paint; the usual `localStorage` fix is an inline `<head>` script, which would saddle Phase 10's CSP with `script-src 'unsafe-inline'` for a UI preference. And a resizing rail has no `transform` equivalent — it is one user-initiated layout change, not decoration, so it is animated and disabled under reduced motion | A fixed-height dashboard at every viewport (clips on short windows — worse than scrolling), letting home scroll on desktop (the panels then sit below the fold on the app's front door), `localStorage` + an inline bootstrap script (CSP debt), snapping the rail with no transition (a 136px jump reads as a glitch) |

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
