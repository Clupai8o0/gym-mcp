# @tempo/api

The Tempo backend: one FastAPI service exposing **REST**, the **MCP server**, and the
**OAuth 2.1 AS** as thin adapters over a shared `app/services` layer ("one Python brain").
Python 3.13, fully async. Reference: [`docs/03-backend-fastapi.md`](../../docs/03-backend-fastapi.md).

## Local development

Python deps are managed by [uv](https://docs.astral.sh/uv/) (not pnpm). From this directory:

```bash
uv sync                       # create .venv and install deps (incl. dev group)
uv run uvicorn app.main:app --reload --port 8000
curl localhost:8000/api/health   # -> {"status":"ok"}
```

## Checks

These are also wired into Turborepo (`pnpm exec turbo run lint typecheck test` from the repo root):

```bash
uv run ruff check . && uv run black --check .   # lint + format check
uv run mypy                                     # types (strict)
uv run pytest -q                                # tests
```

## Layout (grows by phase — see docs/03)

```
apps/api/
├── app/
│   ├── main.py      # create_app(): FastAPI factory (+ /api/health)
│   ├── core/        # config, db, security, logging, errors   (Phase 2+)
│   ├── models/      # SQLAlchemy models                        (Phase 1)
│   ├── schemas/     # Pydantic I/O models                      (Phase 2)
│   ├── services/    # ALL business logic (shared by REST + MCP)(Phase 2)
│   ├── api/routers/ # thin REST endpoints                      (Phase 2)
│   ├── mcp/         # MCP server                               (Phase 5)
│   ├── oauth/       # OAuth 2.1 AS                             (Phase 3)
│   └── auth/        # Google OIDC + web session               (Phase 3)
├── migrations/      # Alembic                                  (Phase 1)
├── tests/
├── index.py         # Vercel entrypoint: exposes `app`
└── pyproject.toml   # uv-managed; uv.lock committed
```
