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
## Phase 6 — Slice: Design system + app shell + Library — IN PROGRESS (built + self-verified; **Antigravity frontend-review gate + live authed render outstanding**)
- **Branch/PR:** `phase-6-design-library` (cut from `phase-5-mcp-server` HEAD, since Phase 5 is
  not yet merged to `main`; committed locally, push + PR pending human go-ahead).
- **⚠️ Gate not yet satisfied:** this phase's gate is the **Antigravity frontend review** (docs/08
  rubric). The code is complete, builds, and the design system + marketing shell render correctly
  (screenshotted); the Antigravity pass and a **live render of the authenticated Library against a
  seeded Neon DB + real Google session** wait on the same external prereqs as Phases 3–5 (Neon
  provisioning, Google OIDC client) — the app is verified against the real API contract, not yet a
  live logged-in session.
- **Scope (shipped):**
  - **Design system:** `getdesign x.ai` installed → `apps/web/DESIGN.md` (the x.ai spec). Token
    layer `design/tokens.css` (color/space/radius/type/motion as CSS custom properties, dark
    signature + light variant), `design/motion.ts` + `design/easings.ts` (durations/spring/curves
    mirrored for the `motion` lib), `app/globals.css` (reset + View-Transitions rules + reduced
    motion). **Tokens-only** styling via CSS Modules — no hardcoded hex/px/ms in components.
  - **`components/ui/`** wrappers: `Button` (pill, 3 variants + loading/disabled), `Card`, `Input`,
    `Select`, `Badge` (muscle/equipment/custom tones), `Skeleton`, `EmptyState`, `Spinner` — each
    with all states + focus-visible + reduced-motion.
  - **`components/motion/`** primitives: `FadeIn`, `Stagger` (CSS enters), `Pressable`, `Sheet`
    (`motion` lib, interruptible), `SharedElement` (React `<ViewTransition>` behind a typed,
    gracefully-degrading wrapper). All reduced-motion aware; used by the Library.
  - **App shell:** authed `(app)` route-group layout (`requireUser` → redirects to the API's Google
    login when signed-out; app chrome never renders for signed-out users), sticky anchored header
    (`AppHeader` + `AppNav` active-state + `UserMenu` sign-out), view-transition wrapper. Signed-out
    `(marketing)` landing page (hero + feature trio). Placeholder `/log` + `/dashboard` so nav has
    no dead links (replaced in Phases 7–8).
  - **Library surface:** grid of `ExerciseCard`s (illustration + name + muscle/equipment tags) with
    `IllustrationImage` placeholder/generating/ready states (no CLS); `FilterBar` (search debounced,
    muscle/equipment/category/level) **synced to the URL** (shareable + back-button; mobile filters
    in a `Sheet`); server-side pagination; detail `[slug]` page (large illustration, ordered
    instructions, target muscles, the user's PRs, "Log this" affordance) with the **list→detail
    shared-element morph**; `loading.tsx` + `not-found.tsx`.
  - **Typed API client:** `lib/api-types.ts` **generated from the FastAPI OpenAPI schema**
    (`openapi.json` → `openapi-typescript`; `pnpm gen:api`) — **no `any` at the boundary**. Server
    reads forward the session cookie (`lib/api.ts`); `lib/{auth,format,catalog,cn,env}.ts` helpers.
  - **Additive API (D25):** `GET /api/exercises/by-slug/{slug}` + `services/exercises.get_by_slug`
    (slug→exercise stays in `services/`); the only backend change, fully test-backed.
  - **Antigravity rubric codified** in `apps/web/FRONTEND_REVIEW.md` (docs/08 DoD).
- **DoD evidence:**
  - **`pnpm --filter @tempo/web run build lint typecheck` → all green.** `next build` compiles +
    typechecks; `/` prerenders static, `/library`, `/library/[slug]`, `/log`, `/dashboard`
    correctly **dynamic** (session-gated). ESLint (incl. `react-hooks/set-state-in-effect`) + `tsc
    --noEmit` clean.
  - **API still green with the additive change:** `uv run pytest -q` → **184 passed** (was 180 →
    **+4**: `get_by_slug` service global-over-custom + not-found, and the `by-slug` router 200/404);
    `ruff` + `black --check` + `mypy` (strict) clean. Architecture guard + MCP↔REST contract suite
    unaffected.
  - **Live render:** `next start` + browser screenshot of `/` confirms the x.ai aesthetic renders —
    near-black canvas, Inter display with negative tracking, Geist-Mono uppercase eyebrows, accent
    pill CTA, hairline cards; **no console errors/hydration warnings**.
- **Outstanding (gated on external prereqs — Neon DB + Google OIDC client, same as Phases 3–5):**
  - [ ] **Antigravity frontend-review** pass against `apps/web/FRONTEND_REVIEW.md` (docs/08 gate).
  - [ ] Live render of the authenticated Library against a **seeded Neon catalog** + real Google
        session (grid, URL-synced filters, list→detail morph, PRs on the detail page).
  - [ ] Lighthouse/CWV budget check (LCP<2.5s, CLS<0.1, INP<200ms) on the deployed preview.
- **Notes / decisions:** logged **D24** (getdesign = spec not lib; dark-signature + light variant;
  CSS-Modules tokens-only; motion split) and **D25** (additive `by-slug` endpoint) in `01`. New web
  deps: **`motion`** (interruptible primitives), **`openapi-typescript`** (dev, type-gen). Enabled
  `experimental.viewTransition` + Blob `images.remotePatterns` in `next.config.ts`. Uses the
  existing `NEXT_PUBLIC_API_URL` / `API_INTERNAL_URL` env (already in `.env.example`).
## Phase 7 — Slice: Log a workout (UI + MCP parity) — IN PROGRESS (built + self-verified; **Antigravity frontend-review gate + live authed render outstanding**)
- **Branch/PR:** `phase-7-log-workout` (cut from `phase-6-design-library` HEAD, since Phase 6 is
  not yet merged to `main`; committed locally, push + PR pending human go-ahead).
- **⚠️ Gate not yet satisfied:** this phase's gate is the **Antigravity frontend review** (docs/08
  rubric). The code is complete, builds, lints, and typechecks; the **Antigravity pass** and a
  **live render of the authenticated Log flow against a seeded Neon DB + real Google session** wait
  on the same external prereqs as Phases 3–6 (Neon provisioning, Google OIDC client) — the app is
  verified against the real API contract, not yet a live logged-in session.
- **No backend change:** every surface the Log slice needs (`POST/GET /api/sessions`,
  `GET /api/sessions/{id}` detail-with-sets, `POST /api/sessions/{id}/sets` → `LoggedSetOut` with
  the PR verdict, `PATCH/DELETE /api/sets/{id}`, `GET /api/exercises`) shipped in Phases 2/5, and
  the **MCP↔REST contract suite + full log-a-workout-over-the-wire test** shipped in Phase 5 already
  prove chat parity. Phase 7 is a pure frontend slice (D26).
- **Scope (shipped):**
  - **Log home (`/log`):** server-rendered — lists recent sessions; surfaces today's session as a
    prominent **Continue** card (or a `SessionStarter` when none). `?exercise=<slug>` (from the
    Library "Log this") is threaded through so the movement is pre-added on arrival.
  - **Active-session surface (`/log/[sessionId]`):** the `SessionLogger` (client) seeds its view
    model from the server `SessionDetail`, then evolves it with **optimistic** writes:
    `ExercisePicker` (debounced catalog search in a `Sheet`), `ExerciseBlock` per movement, and the
    **`SetEntryPad`** (big one-handed numeric entry via `NumberField`, reps/hold mode, opt-in RPE,
    **previous set pre-fills the next**). Deep-link `?add=<slug>` pre-adds an exercise.
  - **PR celebration (signature moment, docs/08):** on a set that sets a record, `PrCelebration`
    plays an accent bloom + `CountUp` of the new value on the set row — <500ms, spring, and skippable
    under reduced motion (gradient-free bloom per the craft rubric).
  - **Rest timer** (nice-to-have): compact `RestTimer` starts on each set save, +30s / skip,
    slides up via `motion`, reduced-motion cross-fade.
  - **Offline-first logging (PWA, D27):** `lib/offline` — an IndexedDB write-queue keyed by the
    optimistic row's client id; when a `log_set` can't reach the API it's queued and the row shows
    **Queued**, then flushed on the `online` event, reconciling the server's PR verdict back into
    the row (`useOfflineQueue`, connectivity via `useSyncExternalStore`). `SyncStatus` surfaces
    offline/pending state. A **minimal service worker** (`public/sw.js`) makes the app installable
    + serves the offline shell (never touches the API origin); `manifest.webmanifest` + a token-
    colored `icon.svg` added. Install polish + real PNG icons are deferred to Phase 9 (per docs/10).
  - **Browser mutation client (`lib/client.ts`, D26):** typed off the generated OpenAPI schema
    (`createSession`/`logSet`/`updateSet`/`deleteSet`/`searchExercises`/`getExerciseBySlug`), with
    `credentials:'include'` + the `X-Tempo-Client` CSRF header; `NetworkError` vs `ClientApiError`
    split drives queue-vs-surface-error. Server reads (`listSessions`/`getSession`) added to
    `lib/api.ts`. Log-specific view model in `components/log/types.ts`; `lib/format` gained
    relative-date/duration/clock/set-summary helpers.
  - States: loading (`[sessionId]/loading.tsx` skeleton), not-found (`[sessionId]/not-found.tsx`,
    auth-scoped), empty (no exercises / no results), error (per-set `Retry`), placeholder — all
    present. Tokens-only styling; every animation composed from `components/motion` + tokens.
- **DoD evidence:**
  - **`pnpm --filter @tempo/web run build lint typecheck` → all green.** `next build` compiles +
    typechecks; `/log` + `/log/[sessionId]` correctly **dynamic** (session-gated), `/` still static.
    ESLint (incl. the React-19 `react-hooks/*` purity + set-state-in-effect rules) + `tsc --noEmit`
    clean. No `any` at the API boundary (types from `lib/api-types`).
  - **API unchanged + still green:** `uv run pytest -q` → **184 passed** (no backend edits this
    phase); the Phase 5 MCP↔REST contract suite + `test_mcp_transport`'s full log-a-workout loop
    remain the parity evidence (a set logged from the UI hits the same `sessions`/`sets` services
    a chat `log_session`/`log_set` does).
- **Outstanding (gated on external prereqs — Neon DB + Google OIDC client, same as Phases 3–6):**
  - [ ] **Antigravity frontend-review** pass against `apps/web/FRONTEND_REVIEW.md` (docs/08 gate) —
        incl. the Phase-7 signature moment (PR celebration <500ms).
  - [ ] Live authed render: start a session, add exercises, log sets (optimistic + PR feedback)
        against a **seeded Neon catalog** + real Google session; confirm the same workout logged via
        the claude.ai MCP connector lands identically in Neon.
  - [ ] Offline demo: log sets with the network off → **Queued**, then reconnect → synced with PR
        verdicts (the IndexedDB queue is unit-shaped but the live round-trip needs the deployed API).
  - [ ] Lighthouse/CWV budget check (LCP<2.5s, CLS<0.1, INP<200ms) on the deployed preview.
- **Notes / decisions:** logged **D26** (browser mutation client + no new backend; API is the single
  write path) and **D27** (app-managed IndexedDB offline queue; minimal SW; install polish → Phase 9)
  in `01`. New web dep: **none** (uses the existing `motion` + generated types). No new env, no
  migration, no `.env.example` change. Added `manifest.webmanifest`, `public/sw.js`, `public/icon.svg`.
## Phase 8 — Slice: Dashboard + Skills module — IN PROGRESS (built + self-verified; **Antigravity frontend-review gate + live authed render outstanding**)
- **Branch/PR:** `phase-8-dashboard-skills` (cut from `phase-7-log-workout` HEAD, since Phase 7 is
  not yet merged to `main`; committed locally, push + PR pending human go-ahead).
- **⚠️ Gate not yet satisfied:** this phase's gate is the **Antigravity frontend review** (docs/08
  rubric). The code is complete, builds, lints, and typechecks; the **Antigravity pass** and a
  **live render of the authenticated Dashboard/Skills/Settings against a seeded Neon DB + real
  Google session** wait on the same external prereqs as Phases 3–7 (Neon provisioning, Google OIDC
  client) — the app is verified against the real API contract, not yet a live logged-in session.
- **Backend (additive, test-backed — no migration):**
  - **PRs carry their illustration** (D28): `PrOut` gained `illustration_url`/`illustration_status`/
    `is_custom`, read from the exercise `prs.list_prs` already joins — so both REST `/api/prs` **and**
    the MCP `get_prs` tool return the art (the MCP↔REST contract test still asserts equality).
  - **Units toggle**: `services/users.update_preferences` + `PATCH /api/me` (`MeUpdate`, `kg|lb`).
  - **Connected apps** (D29): new **user-scoped** `services/connections` over the OAuth tables —
    `GET /api/connections` (active grants: name, connected/last-active, live-token count) +
    `DELETE /api/connections/{client_id}` (revokes **only the caller's own** access+refresh tokens).
    Reuses the AS's `revoked_at` mechanism; **no change to issuance/PKCE/rotation** → Phase 3 sign-off
    unaffected. New `connections` router registered in `main.py`; both are thin adapters (guard passes).
- **Frontend (the slice):**
  - **Dashboard (`/dashboard`):** server-rendered — **PRs** grid (`PrList`, one card per exercise with
    its illustration + records, freshest first), **Volume** (`VolumeChart`: three totals + a ranked
    top-8 bar list) and **Frequency** (`FrequencyHeatmap`: Monday-anchored week cells, token-driven
    `color-mix` intensity). One **`RangeControl`** (30D/3M/6M/1Y) drives both charts via a URL-synced
    `?range=` (shareable, like the Library filters); `loading.tsx` skeleton.
  - **Skills (`/dashboard/skills`):** `SkillsBoard` grid of `SkillRing`s (SVG progress ring, stage over
    total); tapping one opens `SkillEditor` in a right `Sheet` (stage select + percent slider + stage
    name + notes) that PUTs `/api/skills/{slug}/progress` and updates the ring in place. `DashboardTabs`
    sub-nav (Overview / Skills — the secondary module).
  - **Settings (`/settings`):** `UnitToggle` (optimistic `PATCH /api/me` + `router.refresh()`),
    **Connected apps** = `ConnectorCard` (copy-able `…/mcp` URL + "Add to Claude" steps) + `ConnectionsList`
    (revoke with an inline two-step confirm — no native dialog — removing the row once tokens are revoked),
    and `AccountCard` (identity + sign-out). Reached from the header avatar (`UserMenu` → `/settings`).
  - **Typed client:** `lib/api-types.ts` regenerated from the FastAPI OpenAPI (`openapi.json`) so the new
    endpoints + `PrOut` fields are typed — **no `any` at the boundary**. New server reads (`listPrs`,
    `getVolume`, `getFrequency`, `getSkillsOverview`, `listConnections`) in `lib/api.ts`; browser mutations
    (`updateSkillProgress`, `updatePreferences`, `revokeConnection`) in `lib/client.ts`; `lib/ranges.ts` +
    `formatTonnage`/`formatCount`/`formatWeekLabel` helpers. Tokens-only styling; motion via the shared
    primitives (`Stagger`/`Pressable`/`Sheet`) + reduced-motion; all states (loading/empty/error) present.
- **DoD evidence:**
  - **`next build` green** — `/dashboard`, `/dashboard/skills`, `/settings` compile + typecheck as
    **dynamic** (session-gated); `/` still static. ESLint (incl. React-19 `react-hooks/*`) + `tsc --noEmit`
    clean; Prettier clean over all authored files (`openapi.json` + `api-types.ts` are prettier-ignored,
    generated).
  - **API `uv run pytest -q` → 195 passed** (was 184 → **+11**): connections **service** (list groups per
    client + first/last activity, revoke kills the access token + is idempotent, unknown-client 404, and
    **cross-user scoping** — an intruder can't revoke another user's grant), connections **router**
    (list/revoke/empty/404), `PATCH /api/me` (updates + rejects a bad unit), and the PR list now asserting
    the illustration fields. `ruff` + `black --check` + `mypy` (strict, 129 source files) clean. The
    **architecture guard** + **MCP↔REST contract** suites still pass (`get_prs` == `/api/prs` with the new
    fields on both sides).
  - **`app.openapi()` builds cleanly — 28 paths**, incl. `GET /api/connections`,
    `DELETE /api/connections/{client_id}`, and `PATCH /api/me`; `PrOut` carries the three art fields;
    `ConnectionOut` shape verified.
- **Outstanding (gated on external prereqs — Neon DB + Google OIDC client, same as Phases 3–7):**
  - [ ] **Antigravity frontend-review** pass against `apps/web/FRONTEND_REVIEW.md` (docs/08 gate).
  - [ ] Live authed render: dashboard reflects **real Neon analytics** (PRs with art, volume across the
        selected range, the frequency heatmap); skills read/write persists; **connected-apps revoke against
        a live claude.ai grant actually kills the token** (the revoke path is service-tested with a minted
        token; the live claude.ai round-trip needs the deployed API + real client).
  - [ ] Lighthouse/CWV budget check (LCP<2.5s, CLS<0.1, INP<200ms) on the deployed preview.
- **Notes / decisions:** logged **D28** (additive `PrOut` art fields, REST+MCP in lockstep) and **D29**
  (Settings/Connected-apps are REST-only account-management; user-scoped revoke over the existing hashed-token
  tables — no AS-semantics change) in `01`. New web dep: **none** (uses the existing `motion` + generated
  types). No new env, **no migration** (reads existing `illustration_*` columns / OAuth tables; updates the
  existing `unit_pref`). Regenerated `apps/web/openapi.json` + `lib/api-types.ts`.
## Phase 9 — Flagship polish pass — IN PROGRESS (built + self-verified; **Antigravity final review + live authed render / Lighthouse outstanding**)
- **Branch/PR:** `phase-9-polish` (cut from `phase-8-dashboard-skills` HEAD, since Phase 8 is not
  yet merged to `main`; committed locally, push + PR pending human go-ahead).
- **⚠️ Gate not yet satisfied:** this phase's gate is the **final Antigravity frontend review** across
  every surface (docs/08 rubric). The code is complete, builds/lints/typechecks clean, and the
  renderable public surfaces are screenshot-verified; the Antigravity pass, a **live authed render**,
  and the **Lighthouse/CWV check on a deployed preview** wait on the same external prereqs as Phases
  3–8 (Neon provisioning, Google OIDC client, deploy).
- **Approach:** ran **four parallel read-only audits** (motion & signature moments · component states
  & a11y · performance/CWV · PWA/offline/aesthetic) against the `08` rubric + `FRONTEND_REVIEW.md`,
  then executed the deduplicated findings. Baseline was already strong (token discipline clean, motion
  layer solid, states/loading broadly covered) — this pass closed the gaps and raised craft.
- **Scope (shipped) — pure frontend slice; no backend/API/migration change:**
  - **Error + loading states (rubric §4):** added the missing **error boundaries** — root
    `app/global-error.tsx` + shared `app/(app)/error.tsx` (Next 16 `unstable_retry`), a new reusable
    `ui/ErrorState`, a branded root `app/not-found.tsx`, and the **three missing `loading.tsx`
    skeletons** (`/log`, `/settings`, `/dashboard/skills`). `EmptyState` gained a `titleAs` so
    full-page not-founds start at `h1`.
  - **PWA install polish (docs/10; deferred from Phase 7):** generated the real **icon set** — `192`,
    `512`, dedicated **maskable** (full-bleed, mark in the 80% safe zone), **`apple-touch-icon` (180)**,
    and `favicon-16/32` — via a committed, reproducible `scripts/generate-icons.mjs` (sharp). Rewrote
    `manifest.webmanifest` (`id`, `lang`/`dir`, `categories`, `shortcuts`, all icon purposes) and the
    layout `icons`/`apple` metadata. **Install affordance** `pwa/InstallCard` (captures
    `beforeinstallprompt`; iOS "Add to Home Screen" copy; hides when standalone). **Service-worker
    hardening:** only cache `ok`+`basic` responses (no more poisoning), a dedicated static **`/offline`**
    fallback + per-URL navigation cache (replacing the single overwritten key), cache bump `v2`, and a
    `Cache-Control: no-cache` header on `/sw.js`. **Global `OfflineIndicator`** chip in the header +
    `useOnline` hook; iOS **safe-area** (`viewport-fit: cover` + header inset); **unified 3-bar `Logo`**
    reused by the header + marketing so the in-product mark matches the app icon.
  - **Accessibility (WCAG AA):** `--text-muted` nudged `#7d8187 → #868a90` to clear 4.5:1 on the
    elevated `--surface`/`--surface-2` fills (it failed there); new `--input-border` (`#676b71` dark /
    `#8b8d93` light) gives form controls a **3:1** resting boundary (1.4.11); `Sheet` got a real **focus
    trap + background `inert`**; `ExercisePicker` dropped the misused listbox/option ARIA; destructive
    `ConnectionsList` confirm now moves focus to Cancel + announces via `role="alert"`; added a **skip
    link** + `#main`; `aria-expanded` on dialog triggers; `UserMenu` label-in-name fixed; the global
    focus ring no longer rewrites `border-radius` (was reshaping pills).
  - **Motion rulebook:** `Sheet`/`RestTimer` exits now accelerate with `--ease-in` (were reusing
    ease-out); `SetRow` gained a symmetric exit via `AnimatePresence`; tokenized the count-up
    (`--dur-count`), ambient loops (`--dur-loop`), and press scales (`--press-scale*`); the reduced-motion
    `Spinner` keeps a gentle spin (was frozen by the global reset → read as "stuck"); **removed the two
    gradients** (Skeleton shimmer → opacity pulse; illustration placeholder → flat) per the craft rubric;
    marketing stagger 60 → 40ms; `FrequencyHeatmap` gained an entrance reveal; hoisted the celebrate
    timeout to a named constant.
  - **Performance / CWV:** first Library row now eager-loads (`priority`) as the LCP candidates;
    **`motion` removed from the Library/Dashboard initial bundles** (`Pressable` → pure-CSS `:active`;
    `Sheet` `next/dynamic`-imported in `FilterBar`/`SkillEditor`); the detail page streams the hero
    immediately with the PRs behind `<Suspense>` (no longer LCP-blocking); session page parallelized
    with `Promise.all`; `next.config` images tuned (**AVIF**, 1-year `minimumCacheTTL`, trimmed
    device/image sizes); `SyncStatus` de-`"use client"`-ed.
- **DoD evidence:**
  - **`next build` → success**, 9 static pages generated; `/` + `/offline` prerender **static** (the
    SW precaches `/offline`), all authed routes correctly **dynamic**. `tsc --noEmit` + `eslint .` clean.
  - **Icons verified** at correct dimensions (192/512/maskable/apple-touch/favicons); maskable mark sits
    inside the safe zone (visually checked).
  - **Public surfaces screenshot-verified** on `next start`: marketing (unified Logo, x.ai aesthetic
    intact), the new `/offline` page, and the branded 404 — no console/hydration errors.
  - **API untouched** — no backend edits this phase, so the Phase 8 suite (`195 passed`) and the
    MCP↔REST contract/architecture guards are unaffected; web has no runtime test suite (build+lint+type
    are its gates).
- **Outstanding (gated on external prereqs — Neon DB + Google OIDC client + deploy, same as Phases 3–8):**
  - [ ] **Antigravity final frontend-review** across all surfaces (docs/08 gate), incl. reduced-motion
        verified with the OS setting on and keyboard/focus walk-throughs on the authed pages.
  - [ ] Live authed render of every surface against a **seeded Neon DB + real Google session** (the
        contrast/motion/perf changes verified in a real logged-in session).
  - [ ] **Lighthouse/CWV** budget check (LCP<2.5s, CLS<0.1, INP<200ms) on the deployed preview.
  - [ ] Live install (Android `beforeinstallprompt` + iOS A2HS) and an offline navigation hitting the
        `/offline` fallback on the deployed PWA.
- **Notes / decisions (logged as D30 in `01`):** three deliberate balances — (a) `--input-border` at a
  visible 3:1 for functional form controls (a11y 1.4.11) while decorative card hairlines stay `--border`;
  (b) **did not** cache catalog reads (perf audit M3) because `list/get exercises` include per-user custom
  rows — correctness over the TTFB win; (c) **kept `motion` out of the app-shell nav** — no `layoutId`
  sliding tab indicator (motion audit #7), since that would reintroduce `motion` to every authed page's
  initial bundle, undoing the perf work; the snap indicators stay. New web deps: **none** (sharp for the
  icon script is transitive via Next). No new env, **no migration**.
## Phase 11A — Session lifecycle — DONE (verified on local Postgres)
- **Branch/PR:** `phase-11a-session-lifecycle` (cut from `phase-9-polish` HEAD, since Phase 9 is not
  yet merged to `main`; committed locally, push + PR pending human go-ahead).
- **Why:** a session had `performed_at` and nothing else, so "is a workout in progress?" was
  `isToday(performed_at)` **inside a server component** — it evaluated in the server's timezone
  (UTC in production). Observed in the running app: training at 5 pm in UTC−8 reads as "tomorrow"
  (no Continue card → a duplicate session), a workout finished at 7 am still reads "In progress" at
  11 pm, and `duration_minutes` rendered on the recent-workouts list although **nothing ever wrote it**.
- **Scope (shipped):**
  - **Migration `0004_session_ended_at`** — additive, reversible `workout_sessions.ended_at
    TIMESTAMPTZ NULL`. No backfill: existing rows read as never-finished and the read-time
    staleness rule retires them (D31). `docs/02` DDL updated.
  - **`services/sessions`** — `finish_session()` (stamps `ended_at`, derives + stores
    `duration_minutes`, **idempotent**) and `get_active_session()` (newest row with `ended_at IS
    NULL`; sweeps anything untouched >`STALE_AFTER` = 12 h, dating the close from that session's
    last set). **No date arithmetic or timezone logic survives anywhere in the resolution path.**
  - **REST** — `GET /api/sessions/active` (declared *before* `/{session_id}` so the literal wins)
    returning `ActiveSessionOut {session: SessionOut | null}`, and `POST /api/sessions/{id}/finish`.
    Both thin adapters; `SessionOut` gained `ended_at`. `docs/03` surface table updated.
  - **MCP** — `get_active_session` + `finish_session` tools (write scope on finish), same services,
    same schemas; `tempo://guide` gained a "Session lifecycle" section telling a model to check for
    an active session before starting one. `docs/04` tool table updated (15 → **17 tools**).
  - **Frontend** — `lib/api.getActiveSession()` (React-`cache`d) + `lib/client.finishSession()`;
    `/log` resolves the Continue card from the lifecycle flag instead of `items.find(isToday(…))`;
    new `components/log/FinishWorkout` in the session logger (separated from "+ Add exercise" by a
    rule so Finish is never the button under a mistimed thumb; shows a "Workout finished · 1 h 27
    min" chip afterward, and flags any sets still in the offline queue). `openapi.json` +
    `lib/api-types.ts` regenerated (**28 → 30 paths**). **`isToday` deleted** from `lib/format.ts`.
- **DoD evidence:**
  - **Migration:** `alembic upgrade head` → `ended_at timestamptz NULL` present on
    `workout_sessions`; **`alembic check` → "No new upgrade operations detected"** (no drift);
    `downgrade base` → only `alembic_version` remains; **re-`upgrade head` repeatable**; `downgrade
    -1` drops just `ended_at` and re-upgrading restores it.
  - **`uv run pytest -q` → 209 passed** (was 195 → **+14**). New: finish stamps duration, finish is
    idempotent (a second call with a later clock does not move `ended_at`), finish someone else's
    session is 404 *and leaves it untouched*, active = newest unfinished, active is `None` once
    finished, active is user-scoped, a dangling session is auto-finished **from its last set**, one
    without sets falls back to its start, an 11 h-old session **survives** the sweep, and the sweep
    retires older dangling rows while keeping the live one. Plus REST `active`/`finish` (incl. 404)
    and **two MCP↔REST contract tests** — `get_active_session` byte-equals `GET /api/sessions/active`,
    and an MCP `finish_session` round-trips through REST *and* flips REST's `active` to `null`.
  - **Architecture guard + MCP↔REST contract suites still pass**; `tools/list` now asserts **17**.
  - **`ruff` + `black --check` + `mypy` (strict, 135 source files) clean**; web `next build`,
    `eslint .`, `tsc --noEmit` all clean.
  - **Manually verified against local Postgres + a live uvicorn/next pair** (real seeded DB, minted
    dev session cookie): created a session → `GET /active` returned it → `POST …/finish` →
    `ended_at` + `duration_minutes: 1` → **a second finish returned the identical `ended_at`** →
    `/active` rolled to the next unfinished session. A backfilled 3-day-old session was **swept on
    the very next read** (`ended_at = performed_at`, duration 0). Then through the **UI at 393×759**:
    `/log` showed the In-progress card, Continue → **Finish workout** → "Workout finished · 1 h 27
    min", back on `/log` the card was gone and the workout appeared under Recent with its duration.
    Zero page errors on `/log` and `/log/[id]` during the flow.
- **Notes / decisions:** logged **D31** in `01` (lifecycle = `ended_at`; lazy 12 h read-time sweep
  dated from the last set; **no** auto-finish on create — `log_session` is also how chat backfills
  historical workouts; idempotent finish for retry/offline safety). No new dependency, no new env.
- **Carried into 11B:** `/log/[sessionId]` also throws a **hydration error** — `formatTime` uses
  `toLocaleTimeString(undefined, …)` inside the client `SessionLogger`, the same locale bug the
  handover flagged for `formatDate` on `/settings`. Both are fixed together in 11B.

## Phase 11B — Mobile shell: bottom tabs + docked session bar — DONE (built + self-verified; **Antigravity frontend-review gate outstanding**)
- **Branch/PR:** `phase-11b-mobile-shell` (cut from `phase-11a-session-lifecycle` HEAD; committed
  locally, push + PR pending human go-ahead).
- **⚠️ Gate not yet satisfied:** UI phase → the **Antigravity frontend review** (docs/08 rubric,
  `apps/web/FRONTEND_REVIEW.md`) is outstanding, as it is for Phases 6–9. Recorded and carried on
  per the handover's working agreement. Lighthouse/CWV still needs a deploy.
- **Pure frontend — no API, schema, or migration change.**
- **Scope (shipped):**
  - **`TabBar`** — one component, two compositions: a bottom tab bar below 768px (inside the thumb
    arc, `env(safe-area-inset-bottom)` respected) and the **same** nav as a **left rail** at ≥768px.
    Four labelled tabs with line-art icons on a 24px grid — **Home · Library · Log · You**; never
    icon-only. **`Log` is a state, not a destination:** with a live session it takes `--accent` and a
    dot badge (plus an `sr-only` "workout in progress"). The wordmark appears only in the desktop rail.
  - **`SessionBar`** — docked directly above the tab bar (above the content column on desktop) on
    every authed route while a session is live: title · set count · a live elapsed clock, tapping
    through to `/log/[id]`. Driven by **`getActiveSession()`** (11A), never a date. It hides on the
    session's own page, where it would only repeat the header it points at.
  - **Top chrome removed.** `AppHeader` / `AppNav` / `UserMenu` **deleted**; each screen's own title
    row scrolls with the content. Sign-out now lives only in the account card under **You** — it is
    no longer a permanently visible destructive control a thumb-width from the nav. The skip link
    stays, and the offline chip moved into the bottom dock (floating above it, so it costs nothing
    when online).
  - **The locale/timezone hydration bug — fixed as a class, not a case.** `formatDate`/`formatTime`/
    `formatRelativeDate`/`formatWeekLabel` no longer touch `Intl`: `toLocaleDateString(undefined, …)`
    resolves Node's locale on the server and the user's in the browser, and even within one locale
    Node's and Chrome's ICU disagree (`pm` vs `PM`). They are now written out by hand and take an
    explicit `Zone`. The remaining variable — the viewer's timezone — is owned by a new
    **`ui/LocalTime`**, which renders UTC server-side and re-renders local once hydrated via
    `useSyncExternalStore` (`lib/hydration.ts`; no `setState`-in-effect, which the React-19 lint
    rules reject). Adopted at all eight call sites.
  - New layout tokens (`--tabbar-height`, `--sessionbar-height`, `--rail-width`); `--nav-height` now
    belongs to marketing only. Library-detail's sticky media offset and the `app-header`
    view-transition anchor (both dead with the header) removed. `getSession` is React-`cache`d so the
    shell's session bar and `/log/[id]` share one fetch.
- **DoD evidence** (all against the live local stack — real seeded Postgres, minted dev session):
  - **`next build` green** (9 static pages; all authed routes still dynamic), **`eslint .`** and
    **`tsc --noEmit`** clean. API untouched → the Phase 11A suite (**209 passed**) still stands.
  - **Zero console errors and zero hydration warnings** on `/`, `/library`, `/log`, `/dashboard`,
    `/dashboard/skills`, `/settings` **and** on `/log/[id]` + `/library/[slug]`, verified by loading
    each in a real browser and capturing `console` + `pageerror`. **The `/settings` hydration error
    is gone** — and so is the one on `/log/[id]` that this pass also found (same root cause).
  - **At 393×759 the tab bar and session bar are visible without scrolling on every authed route**
    (both are fixed; `.main` reserves their height plus the safe-area inset so nothing hides behind).
  - **Session bar present on `/dashboard`, `/library`, `/settings` while live → absent on all three
    immediately after Finish**, asserted programmatically; and absent on `/log/[id]` by design.
  - **Keyboard walk-through** (393×759): Tab 1 = "Skip to content" → Tabs 2–5 = Home/Library/Log/You
    → Tab 6+ = page content; **every stop shows a 2px solid accent focus ring**; activating the skip
    link moves focus to `#main`.
  - **Reduced motion honoured** — with `prefers-reduced-motion: reduce` the session bar's pulse
    resolves to `animation-name: none`. **Dark signature + light variant** both rendered clean.
  - **≥768px renders the left rail**, not a stretched tab bar (screenshotted at 1280×900: rail with
    wordmark, content column offset, session bar docked at the bottom of that column).
  - Tokens-only styling: no hardcoded hex/ms; only the established hairline `1px`/`2px` and intrinsic
    `rem` icon sizes the existing components already use.
- **Notes / decisions:** logged **D32** in `01` (one nav component for both breakpoints; `Log` as a
  state; hand-rolled date formatting + `LocalTime` rendering UTC-then-local rather than blanking or
  guessing a timezone; session bar suppressed on its own page). No new dependency, no new env.

## Phase 11C — Dashboard becomes home — DONE (built + self-verified; **Antigravity frontend-review gate outstanding**)
- **Branch/PR:** `phase-11c-dashboard-home` (cut from `phase-11b-mobile-shell` HEAD; committed
  locally, push + PR pending human go-ahead).
- **⚠️ Gate not yet satisfied:** UI phase → the **Antigravity frontend review** (docs/08 rubric) is
  outstanding, as for Phases 6–9 and 11B. Lighthouse/CWV still needs a deploy.
- **Pure frontend — no API, schema, or migration change** (every number comes from endpoints that
  already existed).
- **Scope (shipped):**
  - **`/dashboard` is now the summary screen**, top to bottom: compact date + avatar row → the
    **active-session card** (or a Start affordance) → four stats for the last 7 days (Sessions ·
    Tonnage · Sets · PRs) → a seven-day strip → one row for the latest PR → one row for the top
    skill. New `components/home/` (`HomeHeader`, `WorkoutCard`, `WeekStats`, `DayStrip`,
    `HighlightRow`, `HomeWelcome`). The workout is never below the fold.
  - **Sections moved out as-built**, loading + empty states intact: `/progress/volume` (VolumeChart
    **+ the RangeControl**), `/progress/frequency` (FrequencyHeatmap at a new readable `size="lg"`),
    `/progress/records` (PrList), `/progress/skills` (SkillsBoard). `DashboardTabs` and
    `/dashboard/skills` **deleted**; the Home tab now owns `/progress/*`.
  - **Fixed while moving it:** `RangeControl` hard-coded `router.push("/dashboard?range=…")`, so on
    its new pages it would have navigated away — it now rewrites the current path. It appears on
    volume and frequency only; **records is all-time**, and home below 768px shows no range control.
  - **Front door:** `loginUrl()` defaults to `/dashboard` (both marketing CTAs included), and
    `manifest.webmanifest` `start_url` `/log` → `/dashboard` with `shortcuts` re-cut to the two
    places the start URL *isn't* — Log and Library.
  - **New-account empty state:** a fresh account now lands on one line of welcome, **Start your
    first workout**, and **Browse 873 exercises** instead of three empty boxes. Stats, strip and
    highlight rows appear only once there is something to count.
  - **Desktop (≥768px):** the `/progress/*` content renders **inline** in home's right column
    (two columns from 1024px, stacked between 768–1024) — same components, no second set.
  - **Timezone discipline:** the stats window is a **rolling 7 days** (two instants → identical in
    every timezone) rather than a UTC "since Monday"; the strip fetches a 9-day overshoot and
    buckets into local calendar days in the browser (`useHydrated`, same pattern as `LocalTime`).
- **DoD evidence** (live local stack, real seeded Postgres, minted dev sessions):
  - **Home fits 690px at 393px wide with no scroll, populated *and* empty** — measured
    `scrollHeight === clientHeight === 690` **with a live session** (so the docked session bar and
    the tab bar are both on screen), and again on a brand-new account. Trimming the summary gap and
    the shell's bottom breathing room bought the 20px the session bar needed.
  - **Every moved section works at its new route**: `/progress/{volume,frequency,records,skills}`
    all render at 393×690 with zero console/hydration errors, each with its `loading.tsx` skeleton
    and its empty state (verified on the fresh account: "No personal records yet" with a CTA, "No
    sets logged in this range yet").
  - **Range control governs the whole `/progress/volume` page**: clicking **30D** stays on
    `/progress/volume?range=30d` and the page re-renders against the new window. `/progress/records`
    exposes no range control; home at 393px exposes **0** visible range controls.
  - **Sign-in lands on `/dashboard`** — both marketing CTAs resolve to
    `…/oauth/login/google?return_to=%2Fdashboard`; served `manifest.webmanifest` reports
    `start_url: /dashboard`, `shortcuts: [Log → /log, Library → /library]`.
  - **New-account empty state rendered against a real fresh `users` row** (`newbie@tempo.local`,
    zero sessions/PRs) — screenshotted at 393×690.
  - **Home tab shows `aria-current="page"` on `/dashboard`, `/progress/volume` and
    `/progress/skills`.**
  - **`next build` green** (12 routes incl. the four new ones), **`eslint .`**, **`tsc --noEmit`**,
    and **Prettier** clean; **no hydration warnings** on any route at 393×690, 800×900, or
    1280×900. API untouched → **209 passed** still stands.
- **Notes / decisions:** logged **D33** in `01`. Two deliberate trade-offs: (a) the desktop column's
  two extra aggregate queries run on mobile too, because a server render cannot branch on viewport
  width — they are cheap, and the hidden column's `next/image`s are lazy so nothing is fetched for
  them; (b) the "Dashboard" PWA shortcut was dropped rather than reordered, since it would now
  duplicate `start_url`.
- **Deliberately NOT changed — needs an orchestrator decision (see the report):** PR semantics. An
  ascending warm-up (80×8, 90×6, 102.5×3) still returns `is_pr=true` on **every** set, and
  `_detect` in `app/services/sets.py` still returns on the first matching metric so a set that is
  both heaviest *and* highest-rep only records the weight. The handover flags both and says to ask
  first — it is a locked contract ported from the legacy app, so nothing was touched.

## Phase 10 — Deploy & launch — NOT STARTED
