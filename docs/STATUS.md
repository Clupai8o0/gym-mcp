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
      ⤷ the full auth/OAuth stack is **built and verified** (Google calls stubbed in tests);
      **provisioning a real Google OIDC client and setting `GOOGLE_CLIENT_ID/SECRET` +
      `SESSION_SIGNING_KEY`/`TOKEN_HASH_PEPPER`** is the remaining external step before the
      **live claude.ai handshake** + the **human security sign-off** can be recorded.
- [ ] Vercel Blob store (`BLOB_READ_WRITE_TOKEN`) — **Phase 4**
      ⤷ the illustration pipeline (seed + batch + on-demand endpoint) is **built and verified**
      (OpenAI/Blob calls stubbed in tests); **setting `BLOB_READ_WRITE_TOKEN`** is the remaining
      external step before art can be generated/stored.
- [ ] OpenAI API key + GPT Image 2 access — **Phase 4**
      ⤷ **setting `OPENAI_API_KEY`** (+ optional `OPENAI_IMAGE_*` tunables) is the other remaining
      step; together with the Blob token it unblocks the **design sign-off** (exemplars) and the
      **full batch run** — the two outstanding Phase 4 gate items.
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
## Phase 3 — Identity + OAuth 2.1 AS 🔒 — IN PROGRESS (built + self-verified; **awaiting human security sign-off**)
- **Branch/PR:** `phase-3-oauth` (cut from `phase-2-services-rest` HEAD, since Phase 2 is not
  yet merged to `main`; committed locally, push + PR pending human go-ahead).
- **⚠️ Gate not yet satisfied:** this phase's DoD requires a **mandatory human security
  review** (`11`) and a **live claude.ai connector handshake**. The code + automated tests are
  complete and green; the human sign-off and live handshake are **outstanding** and block DONE.
- **Scope (shipped):**
  - **Web login (Google OIDC)** in `app/auth/`: `google.py` (build auth URL, code exchange,
    **full ID-token verification** — RS256/JWKS signature + `iss`/`aud`/`exp`/`nonce`/
    `email_verified`), `session.py` (stateless HMAC-signed httpOnly session cookie + the
    short-lived OIDC-transaction cookie), `routes.py` (`/oauth/login/google`,
    `/oauth/callback/google`, `/oauth/logout`).
  - **OAuth 2.1 AS** in `app/oauth/`: RFC 8414 + RFC 9728 well-knowns; RFC 7591 DCR
    (`/oauth/register`); authorize + consent (`/oauth/authorize`, `/oauth/authorize/consent`)
    with PKCE + a signed-consent CSRF token; token endpoint (`/oauth/token`) for
    `authorization_code` + `refresh_token`; resource-server helpers.
  - **Core AS logic** in `services/oauth.py` (framework-free) + **identity** in `services/auth.py`.
  - **`core/security.py`** — the audited crypto: opaque 256-bit tokens, HMAC-SHA256 at-rest
    hashing (peppered), PKCE S256 verify, signed/`typ`-separated payloads.
  - **Real `current_user`** (bearer **or** session; 401 otherwise) + **CSRF** enforcement on
    cookie-authenticated mutations (`X-Tempo-Client`) replacing the Phase-2 stub.
  - **OAuth-protected `/mcp` guard** (`app/mcp/probe.py`) — 401 + RFC 9728 `WWW-Authenticate`
    PRM pointer when unauthenticated; Phase 5 swaps in the real MCP mount behind it.
  - **Migration `0003_oauth`** — the four AS tables (all credential columns hashed).
- **DoD evidence:**
  - **`pnpm exec turbo run build lint typecheck test --filter=@tempo/api` → 4/4 successful.**
    `ruff` + `black --check` clean; `mypy` (strict) clean over **101 files**.
  - **`uv run pytest -q` → 120 passed** (was 70). New: the **full OAuth e2e** (discovery →
    DCR → authorize → consent → token(PKCE) → call `/mcp` → refresh(rotation) → **reuse → chain
    revocation**); **service-level AS tests** (single-use codes, PKCE reject, expiry, audience
    binding, rotation, reuse→chain revoke); **security-primitive units** (hashing, PKCE,
    signed-payload tamper/expiry/domain-separation); **Google login** (stubbed) incl. state/
    nonce validation; **session + CSRF** boundary; **metadata**, **DCR**, **authorize**, and
    **resource-guard** HTTP tests. Architecture guard extended to the auth/OAuth/MCP adapters.
  - **Migration:** `alembic upgrade head` builds all 4 oauth tables; `alembic check` → **no
    drift** vs `app/models/oauth.py`; `downgrade base` → 0 tables left; re-`upgrade` repeatable.
  - **Well-knowns** serve spec-conformant JSON (`code_challenge_methods_supported:["S256"]`,
    `token_endpoint_auth_methods_supported:["none"]`, issuer = endpoints' base); `/mcp` 401
    carries the PRM pointer.

### Security checklist (`05`) — self-assessed; **HUMAN SIGN-OFF PENDING**
> Each box is implemented + test-backed, but per `11` these are **not** satisfied until a
> **human** reviews `docs/05` line-by-line and records sign-off in the PR. Do **not** deploy
> to production before then.
- [x] **PKCE S256 mandatory**; `plain` rejected; advertised in metadata — `security.verify_pkce_s256`, `oauth.build_authorization_request`; `test_security_primitives`, `test_oauth_service`.
- [x] Auth codes single-use (atomic guarded consume), hashed, ≤60s TTL, bound to client+redirect+PKCE+resource — `oauth.exchange_authorization_code`; `test_oauth_service`, `test_e2e`.
- [x] `redirect_uri` **exact-match** (no substring/open-redirect) — `oauth.build_authorization_request`; `test_authorize_flow`, `test_oauth_service`.
- [x] Access & refresh tokens opaque ≥256-bit, stored only as SHA-256(HMAC) hashes — `security.generate_opaque_token`/`hash_token`, `models/oauth.py`.
- [x] Refresh **rotation** + reuse detection → **chain revocation** (+ live access tokens) — `oauth.refresh_access_token`/`_revoke_chain`; `test_oauth_service`, `test_e2e`.
- [x] Tokens **audience/resource-bound**; resource server checks it — `oauth.resolve_access_token`; `test_oauth_service::test_resolve_rejects_wrong_audience`.
- [x] `state`+`nonce` validated on Google flow **and** signed-request on the AS flow — `auth/routes.py`, `oauth/authorize.py`; `test_login`, `test_authorize_flow`.
- [x] HTTPS-only + cookies `Secure`+`httpOnly`+`SameSite=Lax`+parent-`Domain` — `auth/session.py`, `config.cookie_secure` (Secure auto-on for https origins).
- [x] Cookie-authed mutations CSRF-protected (custom-header-forces-preflight); CORS explicit allowlist, never `*` — `deps.current_user`, `main.py`; `test_session_and_csrf`.
- [x] `/oauth/register` rate-limited; redirect_uris https-validated; registrations logged — `oauth.register_client`; `test_register_endpoint`, `test_oauth_service`.
- [x] Consent shown + recorded per client — `oauth/authorize.py` (structured log; D15); `test_authorize_flow`.
- [x] No secrets/tokens in logs (hashes/ids only) — `core/logging.py` note; services log ids/prefixes.
- [x] Google ID token fully verified (iss/aud/exp/signature via JWKS/nonce) — `auth/google.py`.
- [x] Clock-skew tolerance small + explicit; expiries enforced server-side — `security` (60s skew), `google` (30s leeway).
- [x] Revoked/expired token path tested (401 → client refresh) — `test_oauth_service`, `test_resource_guard`, `test_e2e`.
- [ ] **Human security review complete + signed off in the PR** — *OUTSTANDING (gate).*
- [ ] **claude.ai adds the connector via the live handshake + calls a tool** — *OUTSTANDING (needs real Google client + deploy).*

- **Notes / decisions:** logged **D13–D17** in `01` (stateless session cookie; peppered token
  hashing; consent-logged-not-tabled; the two additive token columns `resource`+`chain_id`;
  authlib for JOSE). New deps: `authlib`, `httpx`, `python-multipart`. New env in
  `.env.example` (issuer/cookie/secret/Google/redirect-allowlist + optional TTL tunables).
  **`ensure_dev_user` is now a test-only helper** (no longer any production auth path).
## Phase 4 — Catalog import + illustration pipeline — IN PROGRESS (built + self-verified; **design sign-off + live batch run outstanding — gated on the OpenAI/Blob prereqs**)
- **Branch/PR:** `phase-4-catalog-images` (cut from `phase-3-oauth` HEAD, since Phase 3 is not
  yet merged to `main`; committed locally, push + PR pending human go-ahead).
- **⚠️ Gate not yet satisfied:** this phase's gate is a **design sign-off on the style
  exemplars** (`06` reference-locking). The prompt template is **locked + committed** and the
  exemplar generator is built (`--exemplars`), but generating the exemplars and the full batch
  needs a real **`OPENAI_API_KEY` + `BLOB_READ_WRITE_TOKEN`** (external prereqs) — so the
  sign-off and the "majority of rows `ready`" DoD line are **outstanding** (analogous to Phase
  3's outstanding human sign-off + live handshake). The **catalog-import half is fully done and
  proven** (below).
- **Scope (shipped):**
  - **Catalog import (fully working):** `app/catalog/dataset.py` (adapter) validates the pinned
    free-exercise-db against a Pydantic schema, maps it to `CatalogRecord` (docs/06 field
    table), reports **enum drift** vs the `exercises` CHECKs, and de-collides slugs
    deterministically; `app/services/catalog.py` **upserts by `(source, source_id)`** (insert /
    update / skip counts), **preserves generated art + custom rows** on re-import.
    `scripts/seed_catalog.py` is a thin CLI over them (unpooled URL; `--source`/`--ref`/
    `--dry-run`).
  - **Illustration pipeline (built + test-backed; awaits keys for a live run):** `app/images/`
    adapters — `prompt.py` (the **LOCKED** monochrome line-art prompt + `STYLE_VERSION` + hash),
    `openai_images.py` (GPT Image 2 via httpx), `blob.py` (Vercel Blob upload to the stable
    `exercises/{slug}.png` key), `cost.py` (batch cost estimate). `app/services/images.py`
    orchestrates: `generate_and_store` (the **shared** single-image routine → status +
    `illustration_url` + `illustration_meta` provenance) and on-demand `ensure` (visibility via
    the catalog service, an **advisory-lock** dedup so concurrent callers can't double-generate,
    ready-skip / in-progress / 503-on-provider-failure). `scripts/generate_illustrations.py`
    (idempotent, resumable, bounded concurrency, per-row commit, cost report, `--exemplars`).
  - **On-demand endpoint:** `POST /api/exercises/{id}/illustration` (thin adapter → `images.ensure`).
  - **`scripts/` is its own `uv` project** (own `pyproject.toml` + `uv.lock`) importing `apps/api`
    via a `sys.path` shim — same `services/` as REST/MCP (D20). New config
    (`blob_read_write_token`, `openai_api_key`, `openai_image_*`) + `.env.example`. Additive
    `unavailable` (503) `ErrorKind` (D19). **No new migration** — Phase 4 fills the existing
    `exercises.illustration_*` columns from `0001`.
- **DoD evidence:**
  - **`pnpm exec turbo run build lint typecheck test` → 7/7 successful** (web cached; api
    build+lint+typecheck+**test**). API `ruff` + `black --check` clean; `mypy` (strict) clean
    over **118 files**.
  - **`uv run pytest -q` → 157 passed** (was 120 → **+37**): catalog upsert (insert/update/skip,
    idempotent re-run, art + custom preservation), dataset parse (mapping, null optionals, drift
    + duplicate-id rejection, slug de-collision), prompt (clauses, body-weight, monochrome
    default, stable hash), cost (docs range), images service (ready-provenance, failed-then-raise,
    ensure generate/ready-skip/in-progress/404/503), and the `POST …/illustration` router
    (200 ready / 404 / 503). Architecture guard extended to the `catalog` + `images` adapters.
  - **Seed proven end-to-end** against local Postgres (an empty DB ≡ an empty Neon branch): after
    `alembic upgrade head`, `seed_catalog.py` → **inserted=873** (= dataset size; DoD "count ≈
    dataset"); **re-run → skipped=873, inserted=0, updated=0** (DoD "re-running changes nothing").
    All 873 global, `illustration_status='pending'`, 873 distinct slugs. The **pinned-SHA network
    fetch** path also verified (`--dry-run` → 873 parsed from `free-exercise-db@b0eed061e1`).
  - **Cost report** builds: 873 × low ≈ **$9.60**, × medium ≈ **$36.70** (docs/06 ~$5–$35 band).
- **Outstanding (gated on external prereqs — `OPENAI_API_KEY` + `BLOB_READ_WRITE_TOKEN`):**
  - [ ] Run `generate_illustrations.py --exemplars` → **design sign-off** on the 5–8 exemplars.
  - [ ] Run the full batch → **majority of rows `ready`** with Blob URLs + `illustration_meta`
        provenance; produce the real cost report.
  - [ ] Live on-demand generation for a custom exercise (endpoint + advisory-lock dedup are
        test-verified with a stubbed provider; only the real OpenAI/Blob round-trip remains).
  - [ ] Confirm the OpenAI Images + Vercel Blob HTTP contracts against current docs before the
        live batch (each adapter flags where).
- **Notes / decisions:** logged **D18** (pinned dataset SHA `b0eed06`), **D19** (additive
  `unavailable`/503 error kind), **D20** (`scripts/` as an independent uv project sharing the
  `services/` brain) in `01`. New deps: **none in `apps/api`** — OpenAI + Blob use the existing
  `httpx`; `scripts/` declares its own (incl. `fastapi`, pulled in transitively by the services
  it calls). `gpt-image-2` pinned as the model default (D8).
## Phase 5 — MCP server (Python) + connector verification — IN PROGRESS (built + self-verified; **live claude.ai connector handshake outstanding — gated on deploy + Google client**)
- **Branch/PR:** `phase-5-mcp-server` (cut from `phase-4-catalog-images` HEAD, since Phase 4 is
  not yet merged to `main`; committed locally, push + PR pending human go-ahead).
- **⚠️ Gate not fully satisfied:** the phase gate is **standard review + a live connector test**.
  The code + automated tests (incl. the MCP↔REST contract suite) are complete and green, and the
  real endpoint is verified over the wire and under a live uvicorn boot; the **live claude.ai
  handshake + the five `04` verification prompts** need a public deploy (Phase 10) and a real
  Google OIDC client (the same external prereqs Phase 3's live handshake waits on).
- **Scope (shipped):**
  - **The MCP server** (`app/mcp/server.py`) — official Python SDK (`mcp` 1.28), `FastMCP`,
    **stateless Streamable-HTTP + JSON responses**. All **15 tools** from the `04` table
    registered, each a ~10-line adapter that calls **the same `services/` function REST calls**
    and returns **the same Pydantic schema** (`search_exercises`, `get_exercise`,
    `create_custom_exercise`, `log_session`, `list_sessions`, `get_session`, `get_session_sets`,
    `log_set`, `get_prs`, `get_pr_history`, `get_volume_summary`, `get_session_frequency`,
    `get_skill_overview`, `get_skill_detail`, `update_skill_progress`) + the **`tempo://guide`**
    resource (`app/mcp/guide.py`).
  - **OAuth-protected mount** (`app/mcp/asgi.py`): a bearer-auth ASGI wrapper reusing
    `services/oauth.resolve_access_token` (REST's exact auth path) — unauthenticated/invalid/
    expired → **401 + RFC 9728 `WWW-Authenticate` PRM pointer**; a token missing the baseline
    `workouts.read` scope → 403; write tools additionally enforce `workouts.write`. Attached as a
    Starlette **`Route("/mcp")`** (exact path, no redirect); the session-manager **lifespan** is
    wired into `create_app()`. DNS-rebinding Host/Origin allowlist on, from settings.
  - **Request runtime** (`app/mcp/runtime.py`): the resolved principal (contextvar) + an
    injectable DB-session source; **no business logic outside `services/`** (architecture guard
    extended coverage passes over `app/mcp`). New `core/db.session_scope()` keeps commit/rollback
    out of the adapters.
  - **Exercise chat-identity rule** (D23): new `services/exercises.resolve_ref` (UUID → slug →
    exact name; global beats custom; tie → candidates), documented in `tempo://guide`.
  - The Phase-3 `/mcp` **probe** (`app/mcp/probe.py`) is **replaced** by the real mount; its
    resource-guard coverage moved to the new MCP transport tests (against the real endpoint).
- **DoD evidence:**
  - **`pnpm exec turbo run build lint typecheck test` → 7/7 successful** (web cached; api
    build+lint+typecheck+**test**). API `ruff` + `black --check` clean; `mypy` (strict) clean
    over **124 files**.
  - **`uv run pytest -q` → 180 passed** (was 157 → **+23**, net of the removed probe test): a
    **9-test transport suite** (unauth 401+PRM, invalid 401, insufficient-scope 403, `tools/list`
    exposes all 15, `resources/read tempo://guide`, catalog search, the **full log-a-workout loop
    with PR detection over the wire**, write-needs-write-scope, spoofed-Host 421); a **13-test
    MCP↔REST contract suite** asserting every read tool's output **equals** its REST endpoint and
    every write round-trips through REST (**anti-drift**); and `resolve_ref` service tests
    (UUID/slug/name, visibility, global-over-custom, ambiguity→candidates).
  - **OAuth e2e** (`test_e2e.py`) now drives the **real** MCP server for its `/mcp` steps: a
    minted access token runs `tools/list`, the rotated token still works (refresh without
    re-auth), and the revoked token → 401.
  - **Live uvicorn boot** (dummy DB): lifespan logs *StreamableHTTP session manager started*;
    `GET /.well-known/oauth-protected-resource` → 200 (`resource` = `…/mcp`); `POST /mcp`
    unauthenticated → **401** with the full `WWW-Authenticate: Bearer resource_metadata=…,
    error="invalid_token"` header; clean shutdown (no cancel-scope error).
- **Outstanding (gated on deploy + real Google client — same prereqs as Phase 3's live test):**
  - [ ] Deploy `api` so `https://api.tempo.clupai.com/mcp` is reachable; add it as a claude.ai
        custom connector; confirm the OAuth handshake (discovery → DCR → Google login → token).
  - [ ] Run the **five `04` verification prompts** end-to-end (search → start session → log sets
        → read PRs) and confirm data in Neon; confirm an expired token refreshes without re-auth.
- **Notes / decisions:** logged **D21** (Route + custom bearer wrapper reusing our resolver,
  principal via contextvar), **D22** (stateless Streamable-HTTP + JSON, Host/Origin allowlist),
  **D23** (`resolve_ref` chat-identity rule) in `01`. New dep: **`mcp` 1.28** in `apps/api`. New
  optional env (`MCP_DNS_REBINDING_PROTECTION`, `MCP_ALLOWED_HOSTS`, `MCP_ALLOWED_ORIGINS`) in
  `.env.example`. **No migration** — Phase 5 adds no schema.
## Phase 6 — Slice: Design system + app shell + Library — NOT STARTED
## Phase 7 — Slice: Log a workout (UI + MCP parity) — NOT STARTED
## Phase 8 — Slice: Dashboard + Skills module — NOT STARTED
## Phase 9 — Flagship polish pass — NOT STARTED
## Phase 10 — Deploy & launch — NOT STARTED
