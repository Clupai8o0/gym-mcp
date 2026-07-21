# 09 — Deployment (Vercel)

Two Vercel projects from **one** repo, each on its own subdomain of `tempo.clupai.com`.

| Project | Root | Framework | Domain | Serves |
|---|---|---|---|---|
| `tempo-web` | `apps/web` | Next.js | **`tempo.clupai.com`** | The UI |
| `tempo-api` | `apps/api` | Python (Fluid Compute) | **`api.tempo.clupai.com`** | REST + `/mcp` + `/oauth/*` + `/.well-known/*` |

The web app calls the API **cross-origin but same-site** (both are subdomains of
`tempo.clupai.com`), so cookies and CORS are straightforward (details below). The MCP client
(claude.ai) talks **only** to `api.tempo.clupai.com`, where the OAuth AS and MCP resource live
on a single origin — the simplest possible shape for the spec.

## Canonical origins (use these everywhere)

| Thing | Value |
|---|---|
| Web origin | `https://tempo.clupai.com` |
| API origin / **OAuth issuer** / MCP resource origin | `https://api.tempo.clupai.com` |
| MCP endpoint | `https://api.tempo.clupai.com/mcp` |
| Protected Resource Metadata | `https://api.tempo.clupai.com/.well-known/oauth-protected-resource` |
| AS Metadata | `https://api.tempo.clupai.com/.well-known/oauth-authorization-server` |
| Google OIDC redirect | `https://api.tempo.clupai.com/oauth/callback/google` |
| Session cookie `Domain` | `tempo.clupai.com` (parent → sent to both subdomains) |

> The FastAPI app builds all absolute URLs (issuer, metadata, redirects) from
> `PUBLIC_BASE_URL=https://api.tempo.clupai.com`. Never emit the raw `*.vercel.app` URL in
> OAuth metadata — claude.ai binds tokens to the issuer it discovered.

## Why subdomains (not a proxy)

`api.tempo.clupai.com` and `tempo.clupai.com` share the registrable domain `clupai.com`, so
they are **same-site**: a session cookie scoped to `Domain=tempo.clupai.com` is delivered to
both, and `SameSite=Lax` still applies. That gives us the cookie convenience of a single origin
**and** a clean, single-origin OAuth/MCP surface on `api.` — without a proxy hop. Cost: the
browser's API calls are cross-**origin**, so the API needs a small CORS policy. (Decision D6,
updated.)

## Cross-origin wiring (CORS + cookies + CSRF)

- **CORS (FastAPI `CORSMiddleware`):** `allow_origins=["https://tempo.clupai.com"]` (plus preview
  origins, see below), `allow_credentials=True`, allow the methods/headers the SPA uses. Do
  **not** use `*` with credentials.
- **Session cookie:** set by the API on the Google callback with `Domain=tempo.clupai.com;
  Secure; HttpOnly; SameSite=Lax`. `api.` is allowed to set a cookie for its parent
  `tempo.clupai.com`; the browser then sends it to both the web and the API. (`api.` sets it,
  everyone under `tempo.clupai.com` receives it.)
- **CSRF:** because auth rides a cookie, require a **custom header** (e.g. `X-Tempo-Client: web`)
  on all state-changing requests. A custom header forces a CORS preflight, and CORS only allows
  our web origin — so a cross-site page cannot forge an authenticated mutation. (Alternative:
  double-submit CSRF token.) SameSite=Lax is a second layer. Document the chosen mechanism in
  `05`.
- **Server-side reads (RSC):** the web server reads the incoming session cookie and forwards it
  on its server-to-server fetch to `api.tempo.clupai.com` (no CORS involved server-side).

## Web project: `apps/web/vercel.ts`

No API rewrites needed (the browser calls `api.tempo.clupai.com` directly). Keep the web config
minimal — framework + security headers + image caching.

```ts
import { routes, type VercelConfig } from '@vercel/config/v1';

export const config: VercelConfig = {
  framework: 'nextjs',
  headers: [
    routes.cacheControl('/icons/(.*)', { public: true, maxAge: '1 week', immutable: true }),
    // add security headers (CSP allowing api.tempo.clupai.com + blob image host, HSTS, etc.)
  ],
};
```
- The web reads `NEXT_PUBLIC_API_URL=https://api.tempo.clupai.com` for browser fetches and
  `API_INTERNAL_URL` (may be the same public URL) for server-side fetches.
- CSP must allow `connect-src https://api.tempo.clupai.com` and `img-src` the Blob host.

> `vercel.ts` is the current recommended config format (replaces `vercel.json`). Verify exact
> `@vercel/config` helper names against the installed version at execution time.

## API project: `apps/api`

- **Entrypoint:** `apps/api/index.py` exposes `app` (FastAPI ASGI). Vercel's Python runtime
  (Fluid Compute) serves it — standard Python 3.13, no edge restrictions.
- Project root = `apps/api`; install via `uv`/`pip` from `pyproject.toml`.
- Attach the custom domain `api.tempo.clupai.com`.
- Fluid Compute reuses instances (fewer cold starts), 300s timeout — but batch image/seed jobs
  still run **offline**, never as a function.
- Keep the DB pool tiny per instance (Neon PgBouncer does the real pooling).
- **CORSMiddleware** configured as above.

## Neon configuration

- **Two connection strings:**
  - `DATABASE_URL` → **pooled** host (`...-pooler.neon.tech`) for the app.
  - `DATABASE_URL_UNPOOLED` → **direct** host for **Alembic** migrations + seed scripts (DDL).
- **Preview isolation:** use **Neon branches** per environment (a `preview`/per-PR branch) so
  migrations/seed run against a throwaway DB; prod points at the primary branch.
- Enable extensions in the baseline migration: `pgcrypto`, `pg_trgm`.

## Vercel Blob

- Create a Blob store; `BLOB_READ_WRITE_TOKEN` used by the offline image job + on-demand
  endpoint. Public blobs → CDN URLs stored in `exercises.illustration_url`. Allow the Blob host
  in the web CSP `img-src`.

## Environment variables

Set per-environment (Development / Preview / Production) with `vercel env`. Never commit secrets.

**`tempo-api`:**
| Var | Purpose |
|---|---|
| `DATABASE_URL` | Neon **pooled** connection (app) |
| `DATABASE_URL_UNPOOLED` | Neon **direct** connection (migrations/seed) |
| `PUBLIC_BASE_URL` | `https://api.tempo.clupai.com` — issuer + absolute URL base |
| `OAUTH_ISSUER` | `https://api.tempo.clupai.com` |
| `WEB_ORIGIN` | `https://tempo.clupai.com` — CORS allowlist + post-login redirect target |
| `SESSION_COOKIE_DOMAIN` | `tempo.clupai.com` |
| `SESSION_SIGNING_KEY` | HMAC key for session cookies (`openssl rand -hex 32`) |
| `TOKEN_HASH_PEPPER` | optional pepper for token hashing |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OIDC |
| `GOOGLE_REDIRECT_URI` | `https://api.tempo.clupai.com/oauth/callback/google` |
| `BLOB_READ_WRITE_TOKEN` | Vercel Blob |
| `OPENAI_API_KEY` | GPT Image 2 (on-demand endpoint) |
| `OPENAI_IMAGE_MODEL` | pinned model id (GPT Image 2) |
| `ALLOWED_REDIRECT_HOSTS` | OAuth client redirect allowlist incl. `claude.ai` (+ future `claude.com`) |

**`tempo-web`:**
| Var | Purpose |
|---|---|
| `NEXT_PUBLIC_BASE_URL` | `https://tempo.clupai.com` |
| `NEXT_PUBLIC_API_URL` | `https://api.tempo.clupai.com` (browser fetches) |
| `API_INTERNAL_URL` | API origin for server-side fetches (usually the same public URL) |

Keep an up-to-date `.env.example` at the repo root enumerating every var (no values).

## Domains, DNS & previews

- DNS: `tempo.clupai.com` → `tempo-web`; `api.tempo.clupai.com` → `tempo-api` (CNAME to Vercel).
- **Google Console:** register `https://api.tempo.clupai.com/oauth/callback/google` as an
  authorized redirect URI; add both origins to authorized JS origins if needed.
- **Previews:** random `*.vercel.app` preview pairs are **cross-site**, so the parent-domain
  cookie trick won't span them. For auth-dependent preview testing, prefer **stable preview
  subdomains** under the real domain (e.g. `staging.tempo.clupai.com` +
  `api.staging.tempo.clupai.com`) with their own Neon branch and Google redirect entry. Non-auth
  UI previews can use the default preview URLs. Document which previews are auth-capable.

## CI/CD

- **Turborepo** builds only affected projects. Vercel Git integration deploys each project on
  push; PRs get preview URLs.
- **Migrations:** run `alembic upgrade head` (against `DATABASE_URL_UNPOOLED` for the target
  branch) as a deploy step / GitHub Action **before** the API serves new code. Never auto-run
  destructive migrations.
- **Type contract:** regenerate the OpenAPI-derived TS client in CI; fail the build on drift.
- **Checks:** lint (ruff + eslint), type (mypy + tsc), tests (pytest + web unit), Lighthouse
  budget on preview.

## Launch checklist (Phase 10 exit)
- [ ] `tempo.clupai.com` serves the web app; Google sign-in works end-to-end (cookie lands on
      `Domain=tempo.clupai.com`, browser→API calls succeed with CORS + credentials).
- [ ] `https://api.tempo.clupai.com/.well-known/oauth-protected-resource` and
      `/.well-known/oauth-authorization-server` return valid JSON with the `api.` issuer.
- [ ] claude.ai adds the connector (`https://api.tempo.clupai.com/mcp`) and logs/reads a workout
      in production.
- [ ] Catalog seeded + images present; on-demand generation works for a new custom exercise.
- [ ] Alembic at `head` on prod Neon; extensions enabled; pooled vs unpooled used correctly.
- [ ] Env matrix complete across Preview + Production; no secrets in the repo.
- [ ] CWV budgets met on the deployed app; error monitoring/logging in place.
