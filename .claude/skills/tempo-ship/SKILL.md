---
name: tempo-ship
description: >-
  How to run Tempo locally and how to get changes safely into production. Use this skill
  whenever you are about to run, verify, commit, push, migrate, or deploy anything in the Tempo
  repo, and also whenever a change touches apps/api/migrations, apps/api/app/services, or the
  production database. Read it BEFORE `git push`, because in this repo a push to main deploys
  both apps automatically and there is no gap afterwards in which to run a migration. Also use it
  when starting the local dev servers, when the API test suite fails at fixture setup, when
  `vercel env pull` returns unusable values, or when production is returning 500s and you need to
  roll back.
---

# Shipping Tempo

Two live Vercel projects, one Neon database, and one property that surprises people: **a push to
`main` is a production deploy.** Everything below follows from that.

## The one rule

```
schema first  →  then push  →  then verify
```

`git push origin main` builds and promotes **both** `tempo-web` and `tempo-api` to production
automatically. There is no approval step and no gap between merging and shipping. So any migration
a change depends on has to already be applied to production Neon **before** the push, not between
the push and a deploy that you were going to trigger later.

This is not hypothetical. On 2026-08-07 the 11N commits were pushed under the belief that pushing
did not deploy. Both apps went out immediately, and `/api/analytics/frequency` returned 500 for an
hour because its `EXISTS` subquery hit a `planned_sets` table that did not exist yet. See the
incident entry in `docs/STATUS.md` under Phase 10.

## Does this change need a migration first?

Ask it before every push. A new table is not the risk on its own; the risk is a **service that
queries it unconditionally**, because that turns a missing table into a 500 rather than a dormant
feature. Check with:

```bash
git diff origin/main --name-only -- apps/api/migrations/          # any new revision?
grep -rn "<NewModel>" apps/api/app/services/ | grep -v services/<its_own_module>.py
```

If a new model appears in any service other than the one that owns it, the code cannot ship before
the schema. 11N was exactly this shape: `planned_sets` had its own `services/plans.py`, but
`analytics`, `sessions`, `exercises` and `corrections` all queried it too.

`GET /api/health` will **not** catch this. It runs `SELECT 1`, so it returns `{"db":"ok"}` against a
schema that is missing half the tables the app needs. Health is a connectivity check, not a
compatibility check.

## Applying a migration to production

`vercel env pull` is a dead end. On CLI 58.4.4 it writes the literal string `"[SENSITIVE]"` in place
of **every** value, including non-secret ones like `NEXT_PUBLIC_API_URL`, and there is no flag to
turn it off. An empty or placeholder URL surfaces downstream as
`sqlalchemy.exc.ArgumentError: Could not parse SQLAlchemy URL from given URL string`, which reads
like a malformed credential and sends you diagnosing the wrong thing. If you see that error, check
whether the URL is empty before concluding anything about its contents.

Get the **direct** (non-`-pooler`) connection string from the Neon console instead. Migrations need
the unpooled URL; the pooled one is for the app.

Do not ask the user to paste it into an interactive prompt. `read` gets EOF in this environment and
silently yields an empty string, which produces the same misleading parse error. Use the clipboard:
ask them to copy the URL, then read it with `pbpaste`, which keeps the credential out of the
transcript, out of `argv`, and out of shell history.

`scripts/migrate-prod.sh` in this skill does the whole thing: validates the shape before touching
anything (rejects empty, `psql '…'`-wrapped, and pooled hosts with a specific reason), runs
`alembic current` / `upgrade head` / `current` / `check`, and pipes every line through a redactor
because SQLAlchemy and asyncpg both embed the DSN in their error messages.

```bash
zsh .claude/skills/tempo-ship/scripts/migrate-prod.sh
```

Afterwards, clear the clipboard (`printf '' | pbcopy`) and verify with
`scripts/verify-prod.py`, which is read-only and checks the two things **`alembic check` does not
compare**: CHECK-constraint names and partial-index predicates. Both have drifted silently in this
repo before, which is why `tests/test_migrations.py` asserts them against real DDL.

## When production is already broken

Roll back first, diagnose second. It takes about two seconds and needs no database credential:

```bash
vercel ls tempo-api                                  # find the previous Ready production build
vercel rollback <previous-deployment-url> --yes
```

Once the schema is ready, roll the **same artifact** forward rather than rebuilding:

```bash
vercel promote <the-new-deployment-url> --yes
```

Read real evidence rather than assuming. Runtime logs give per-path status codes, and their
`"branch":"main"` field is how you confirm a deployment came from a push:

```bash
vercel logs <deployment-url> --json | grep -o '"requestPath":"[^"]*","responseStatusCode":[0-9]*' \
  | sed 's/"requestPath":"//; s/","responseStatusCode":/ -> /' | sort | uniq -c | sort -rn
```

Logs are cumulative for a deployment across every window it was live, so a 500 count alone does not
tell you whether the problem is current. Pull timestamps before concluding it is still broken.

## Deploying manually

Both projects set a Root Directory (`apps/web`, `apps/api`), so `vercel --prod` runs from the **repo
root**. Running it from `apps/web` fails with `path "apps/web/apps/web" does not exist`. After a
push it is also redundant and produces a duplicate deployment.

|             |                                                                    |
| ----------- | ------------------------------------------------------------------ |
| `tempo-web` | root `.vercel` link, Root Directory `apps/web`, Next.js preset     |
| `tempo-api` | `apps/api/.vercel` link, Root Directory `apps/api`, FastAPI preset |

## Running locally

API on `:8000`, web on `:3000`, both reading the root `.env` (symlinked into each app).

```bash
cd apps/api && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000   # background it
pnpm --filter @tempo/web dev                                             # background it
```

Three traps, each of which has cost real time:

**The test suite needs `TEST_DATABASE_URL` exported.** `uv run` does not load `.env`, and
`tests/_dbadmin.py` reads `os.environ` directly, so it falls back to a `postgres` role that does not
exist on this machine and fails at fixture setup:

```bash
TEST_DATABASE_URL=postgresql://clupa@localhost:5432/postgres uv run pytest -q
```

**Never run `next build` while `next dev` is running.** They share `.next`, and the build kills the
dev server. Verify with the dev server, or stop it first.

**`alembic upgrade head` from `apps/api` with no explicit env vars hits your local `tempo_dev`,**
because `migrations/env.py` falls through to `.env`. Always set `DATABASE_URL_UNPOOLED` explicitly.
`os.environ` takes priority over the `.env` fallback, so an explicit export is safe.

## Verifying a frontend change

Check what the server actually sent, not what the source says. Build output and CSS minification
sit between the two, and a removed component can still ship in a stale chunk:

```bash
curl -s http://127.0.0.1:3000/ -o /tmp/page.html
grep -c '<thing-that-should-be-gone>' /tmp/page.html
for c in $(grep -o '/_next/static/css/[^"]*\.css' /tmp/page.html | sort -u); do
  curl -s "http://127.0.0.1:3000$c" | grep -o 'animation-name-or-property'
done
```

The same two commands against `https://tempo.clupai.com` confirm a deploy. If the Chrome extension
is not connected, `open -a "Google Chrome" <url>` plus curl is a fine substitute for a screenshot.

## Keeping the record honest

`docs/STATUS.md` is the live state tracker and it drifts badly, because it is written at the end of
a phase and then not revisited. It has claimed `NOT STARTED` for a phase that had been in production
for six days, listed provisioned prerequisites as open blockers, and asserted the deploy model
backwards — and that last one caused an incident.

When STATUS and the running system disagree, the system is right. Check before trusting it:

```bash
curl -s https://api.tempo.clupai.com/openapi.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['info']['version'], len(d['paths']), 'paths')"
vercel ls tempo-api --prod | head -5
```

Then fix the file in the same change. A tracker that is wrong about whether the product is deployed
is worse than no tracker, because people act on it.
