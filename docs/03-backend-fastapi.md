# 03 — Backend (FastAPI)

The API is one FastAPI app that exposes **REST**, the **MCP server**, and the **OAuth AS** —
all thin adapters over a shared `services/` layer. Python 3.13, fully async.

## Package layout

```
apps/api/
├── app/
│   ├── main.py                 # create_app(): FastAPI, middleware, routers, mounts MCP
│   ├── core/
│   │   ├── config.py           # Settings (pydantic-settings), reads env
│   │   ├── db.py               # async engine + session factory (Neon pooled)
│   │   ├── security.py         # hashing (tokens), PKCE, session cookie signing
│   │   ├── logging.py          # structured logging
│   │   └── errors.py           # exception → HTTP mapping, ServiceError types
│   ├── models/                 # SQLAlchemy models (mirror 02-data-model.md)
│   ├── schemas/                # Pydantic request/response models
│   ├── services/               # ← ALL business logic
│   │   ├── exercises.py
│   │   ├── sessions.py
│   │   ├── sets.py             # includes PR detection
│   │   ├── plans.py            # prescribed sets — the plan, kept out of every derived number
│   │   ├── prs.py
│   │   ├── skills.py
│   │   ├── analytics.py
│   │   └── images.py           # on-demand illustration generation
│   ├── api/
│   │   ├── deps.py             # DI: db session, current_user (session OR bearer)
│   │   └── routers/
│   │       ├── exercises.py
│   │       ├── sessions.py
│   │       ├── sets.py
│   │       ├── planned_sets.py
│   │       ├── prs.py
│   │       ├── skills.py
│   │       ├── analytics.py
│   │       └── health.py
│   ├── mcp/                    # see 04-mcp-server.md
│   ├── oauth/                  # see 05-auth-oauth.md
│   └── auth/                   # see 05-auth-oauth.md (Google OIDC + web session)
├── migrations/                 # Alembic
├── tests/
├── index.py                    # Vercel entrypoint: `from app.main import app`
├── pyproject.toml
└── uv.lock
```

## The service layer contract (the most important rule in this repo)

A **service function** is the *only* place that touches the DB and encodes domain rules.
Both a REST router and an MCP tool call the exact same function. Signature shape:

```python
# services/sets.py
async def log_set(
    db: AsyncSession,
    *,
    user_id: UUID,
    session_id: UUID,
    exercise_id: UUID,
    set_number: int,
    weight_kg: float | None = None,
    reps: int | None = None,
    hold_seconds: int | None = None,
    rpe: float | None = None,
    notes: str | None = None,
) -> SetResult:
    """Insert a set, auto-detect + upsert PRs, return the set and any PR info.

    Rules enforced here (not in the router or tool):
      - session must belong to user_id (else ServiceError.not_found)
      - exercise must be global OR owned by user_id
      - PR detection: compare against personal_records for (user, exercise, metric)
    """
```

Key properties:
- **Takes `db` and `user_id` explicitly** — it does not read request/session state. This is
  what makes it reusable by REST, MCP, and scripts/tests alike.
- **Raises typed `ServiceError`s** (`not_found`, `forbidden`, `conflict`, `validation`) that
  `core/errors.py` maps to HTTP status codes (routers) or MCP error content (tools).
- **No framework imports** (no `fastapi`, no `mcp`) inside `services/`. Pure domain + SQLAlchemy.

## Dependency injection (`api/deps.py`)

- `get_db()` yields an `AsyncSession` from the pooled engine; commits on success, rolls back
  on exception, always closes.
- `current_user()` resolves identity from **either**:
  1. the **web session cookie** (browser calls), or
  2. the **OAuth bearer token** (MCP + programmatic calls) → look up `oauth_access_tokens`.
  Returns a `CurrentUser(user_id, scopes, via)`ues; raises 401 if neither present/valid.
- MCP tools resolve the user from the bearer token via the same token-lookup helper (see `04`).

## REST API surface (v1)

All under the `/api` prefix on the API origin (`https://api.tempo.clupai.com/api/...`). JSON in/out. Pagination
via `?limit=&offset=` (default limit 50, max 100). All list endpoints are user-scoped.

| Method & path | Service | Notes |
|---|---|---|
| `GET /api/health` | — | Liveness + DB ping |
| `GET /api/me` | — | Current user profile + unit_pref |
| `GET /api/exercises` | `exercises.list` | Filters: `q`, `muscle`, `equipment`, `category`, `level`; includes `illustration_url` |
| `GET /api/exercises/{id}` | `exercises.get` | Full detail + instructions |
| `POST /api/exercises` | `exercises.create_custom` | Creates a custom exercise for the user |
| `POST /api/exercises/{id}/illustration` | `images.ensure` | Triggers on-demand generation if missing |
| `GET /api/sessions` | `sessions.list` | Filters: `type`, `from`, `to` |
| `POST /api/sessions` | `sessions.create` | |
| `GET /api/sessions/active` | `sessions.get_active_session` | In-progress session or `null`, with `set_count` + `planned_total`/`completed_count` (11A/11N; declared before `/{id}`) |
| `GET /api/sessions/{id}` | `sessions.get` | Session + sets grouped by exercise |
| `POST /api/sessions/{id}/finish` | `sessions.finish_session` | Stamp `ended_at` + duration, report adherence; idempotent (11A/11N) |
| `PATCH /api/sessions/{id}` | `sessions.update` | title/type/notes/duration |
| `DELETE /api/sessions/{id}` | `sessions.delete` | Cascades sets |
| `POST /api/sessions/{id}/sets` | `sets.log_set` | Auto PR detection |
| `POST /api/sessions/planned` | `plans.plan_session` | Session + prescription, one transaction (Phase 11N; literal, declared before `/{id}`) |
| `GET /api/sessions/{id}/planned` | `plans.get_plan` | The prescription in performance order + each line's completion state |
| `POST /api/sessions/{id}/planned` | `plans.add_planned_sets` | Append lines to an existing prescription |
| `GET /api/sessions/{id}/progress` | `plans.progress` | Planned vs completed, what is left, what is next |
| `PATCH /api/planned-sets/{id}` | `plans.update_planned_set` | Never touches what was logged against it |
| `DELETE /api/planned-sets/{id}` | `plans.delete_planned_set` | Soft; the set it recorded stays, as off-plan work |
| `POST /api/planned-sets/{id}/complete` | `plans.complete` | Writes a real set via `sets.log_set` — normal PR detection |
| `PATCH /api/sets/{id}` | `sets.update` | Recomputes PR if metrics change |
| `DELETE /api/sets/{id}` | `sets.delete` | |
| `GET /api/prs` | `prs.list` | Optional `exercise_id` filter |
| `GET /api/prs/history` | `prs.history` | `exercise_id` + `pr_type` |
| `GET /api/skills` | `skills.overview` | All skills + this user's progress |
| `GET /api/skills/{slug}` | `skills.detail` | |
| `PUT /api/skills/{slug}/progress` | `skills.upsert_progress` | |
| `GET /api/analytics/volume` | `analytics.volume` | `from`,`to`, optional `exercise_id` |
| `GET /api/analytics/frequency` | `analytics.frequency` | Sessions per ISO week, last N weeks; skips deleted and plan-only sessions (11N) |

> The MCP tool set (see `04`) mirrors this table 1:1 plus catalog search — same services, so
> REST and MCP can never diverge. The contract test asserts it.

## Database access

- **Engine:** `create_async_engine(POOLED_DATABASE_URL, pool_pre_ping=True)`. On serverless,
  keep pool size small (e.g. `pool_size=1, max_overflow=…`) and rely on Neon's PgBouncer.
- **Sessions:** `async_sessionmaker(expire_on_commit=False)`. One session per request via DI.
- **Migrations:** Alembic only, against the **unpooled** URL. The app never issues DDL.
- **No lazy loading across await boundaries** — use explicit `selectinload`/joins in services.

## Error handling & validation

- Pydantic v2 schemas validate all inbound REST bodies and query params.
- Services raise `ServiceError(kind, message, details?)`; `core/errors.py` installs an
  exception handler mapping `not_found→404`, `forbidden→403`, `conflict→409`, `validation→422`.
- Never leak internal exceptions to clients; log with a request id, return a generic 500 body.

## Configuration (`core/config.py`)

Read from env (see `09-deployment-vercel.md` for the full matrix). Fail fast on missing
required vars at startup. Minimum: `DATABASE_URL` (pooled), `DATABASE_URL_UNPOOLED`,
`GOOGLE_CLIENT_ID/SECRET`, `SESSION_SIGNING_KEY`, `OAUTH_ISSUER`, `PUBLIC_BASE_URL`
(`https://api.tempo.clupai.com`), `WEB_ORIGIN` (`https://tempo.clupai.com`),
`SESSION_COOKIE_DOMAIN` (`tempo.clupai.com`), `BLOB_READ_WRITE_TOKEN`, `OPENAI_API_KEY`.

**CORS:** `create_app()` installs `CORSMiddleware` with `allow_origins=[WEB_ORIGIN]` (+ stable
preview origins), `allow_credentials=True`, explicit methods/headers (incl. `X-Tempo-Client`).
Never `*` with credentials. The browser authenticates cross-origin (same-site) via the session
cookie; see `05`/`09` for the CORS + CSRF rules.

## Vercel entrypoint

`apps/api/index.py`:
```python
from app.main import app  # FastAPI ASGI app; Vercel Python runtime serves it
```
The `api` project's `vercel.ts`/config points its function at `index.py`. Fluid Compute runs
standard Python (no edge constraints). See `09`.

## Testing (summary; full rules in `12-conventions.md`)

- **Service tests** (the bulk): call service functions directly against a Neon **test branch**
  or local Postgres; assert domain behavior (PR detection, ownership checks).
- **Router tests:** `httpx.AsyncClient` against the app with an authenticated test user.
- **Contract test:** for every MCP tool, assert it calls the same service and returns
  equivalent data to its REST sibling (guards against drift).

## Definition of Done (backend skeleton phase)
- `create_app()` boots; `GET /api/health` returns DB-ping OK against Neon.
- `services/` for exercises + sessions + sets exist with typed signatures and unit tests.
- REST routers for those services pass router tests with a stubbed `current_user`.
- No business logic exists outside `services/`.
