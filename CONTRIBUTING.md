# Contributing to Tempo

The `docs/` folder is authoritative. Read [`docs/11-agent-workflow.md`](./docs/11-agent-workflow.md)
and [`docs/12-conventions.md`](./docs/12-conventions.md) before contributing.

## Prerequisites

- Node ≥ 20 (repo pins **24** in `.nvmrc`) and **pnpm 11** (`corepack enable` recommended).
- **uv** for Python 3.13 (`apps/api`, `scripts/`).

```bash
pnpm install
cd apps/api && uv sync && cd ../..
```

## Branches & commits

- **Branches:** `phase-<n>-<slug>` for execution phases; `fix/…`, `chore/…`, `docs/…` otherwise.
  Never commit straight to `main`.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/) —
  `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `build`, `ci`, `perf`, `style`, `revert`.
  Enforced by commitlint in CI on PRs.
- **PRs:** one per phase; fill in the PR template (acceptance-criteria checklist + gate results).

## Checks (run before pushing)

```bash
pnpm exec turbo run build lint typecheck test
```

| Task        | Web (`@tempo/web`)       | API (`@tempo/api`)              |
| ----------- | ------------------------ | ------------------------------- |
| `build`     | `next build`             | — (Python; served by uv/Vercel) |
| `lint`      | `eslint`                 | `ruff check` + `black --check`  |
| `typecheck` | `tsc --noEmit`           | `mypy` (strict)                 |
| `test`      | — (added with UI phases) | `pytest`                        |

## Guardrails (hard rules — see docs/11)

- **No business logic outside `apps/api/app/services`.** Routers/MCP tools are thin adapters.
- **Keep REST and MCP in lockstep** — both call the same service.
- **Tokens hashed at rest; PKCE mandatory; refresh rotation** (Phase 3, non-negotiable).
- **No batch image/seed jobs on Vercel** — offline scripts only.
- **Idempotent** seeds/migrations; correct **pooled vs unpooled** Neon URLs.
- **No secrets in the repo**; keep `.env.example` current.
- **No non-goals** (teams, billing, social, nutrition) — flag scope creep and stop.

## Definition of Done

A phase is done only when its acceptance criteria (docs/10) pass with evidence, all checks are
green, tests exist at the right layer, the required gate passed, and `docs/STATUS.md` is updated.
