# 13 — Performance: what was slow, what was done, what is left

Audited **2026-08-02** against production by two independent passes (a 36-agent sweep whose
findings were adversarially verified — 17 of 28 survived — and a separate Codex CLI audit read
over the worktree), then **executed the same day**. Where the audit and the measurement disagreed,
the measurement won and the disagreement is recorded rather than smoothed over.

Every number below is **measured**, not estimated. Where something is still an estimate it says so.

---

## The diagnosis

**The functions ran in Virginia. The database is in Sydney.**

```
x-vercel-id: syd1::iad1::…        ← both tempo-web and tempo-api
Neon host:   …ap-southeast-2.aws.neon.tech   (54 ms TCP from Sydney)
```

A request from Australia entered the Sydney edge, was shipped to `iad1` to execute, and reached
back across the Pacific to a database that was 54 ms from the user all along.

One query was not one crossing:

```
GET /.well-known/oauth-authorization-server   0.318 s   ← same function, no DB
GET /api/health          (one SELECT 1)       1.33 / 1.35 / 1.57 s
                                              ───────
                        ≈ 1.0–1.25 s to run one SELECT 1
```

Divided by the ~185 ms `iad1`↔`ap-southeast-2` RTT, that is **six round trips**, which decomposes
exactly: `pool_pre_ping` (BEGIN + `;` + ROLLBACK = 3) + transaction BEGIN + the query itself +
`get_db`'s unconditional COMMIT. **Five of the six were framing. One was work.**

Then multiply: a single authenticated home render issued **ten** API calls, three of them
serialised in the `(app)` layout. `GET /dashboard` — which does nothing but resolve the session
and redirect — measured **1.15 s TTFB**.

Counting statements rather than wall-clock, the Codex pass reached the same place from the other
direction: **≈36 DB protocol exchanges** per dashboard render (16 business SQL + 10 `pool_pre_ping`
+ 10 `COMMIT`). Two methods, one conclusion.

---

## What shipped

### QW1 · Both Vercel projects pinned to `syd1` — **done**

The single change worth more than everything else combined. Toggled in Settings → Functions →
Function Region on both projects, then redeployed.

| | before | after | |
|---|---:|---:|---|
| `/api/health` (one `SELECT 1`) | 1,412 ms | **101 ms** | 14× |
| cost of that `SELECT 1` alone | 1,105 ms | **19 ms** | 58× |
| per DB round trip | 185 ms | **3.2 ms** | 58× |
| `/dashboard` TTFB | 1,150 ms | **222 ms** | 5.2× |
| `/library` TTFB | 5,442 ms | **123 ms** | 44× |

`x-vercel-id` now reads `syd1::syd1::…` on both projects.

> ⚠️ **The region lives only in the Vercel dashboard.** Committing `{"regions": ["syd1"]}` to
> `apps/web/vercel.json` and `apps/api/vercel.json` would put it in the repo, where a project
> recreated from scratch inherits it. Do **not** reach for `vercel.ts` (which `09` prefers):
> `@vercel/config` is not installed and is absent from `pnpm-lock.yaml`, so adding it puts a
> lockfile change on the deploy path and Vercel installs frozen. Plain `vercel.json` is identical
> in effect.

### QW2 + S3 · The component barrels are gone — **done**

`@/components/log` and `@/components/dashboard` each bundled one heavy component with several
light ones, and a barrel import pulls the whole group into the route's client bundle:
`SessionLogger` carries the `motion` runtime; `PrList` → `IllustrationImage` carries the
`next/image` cluster. Both `index.ts` files were **deleted** — every call site now imports the
component it uses — and an ESLint `no-restricted-imports` rule on the two group names stops
someone re-adding them. Barrels elsewhere (`@/components/ui`, `@/components/home`) are fine:
their members are uniformly light.

Per-route client JS, summed from the real Turbopack manifests (`next build` prints no size table):

| route | before | after | |
|---|---:|---:|---|
| `/dashboard` | 88.5 KB gz | **38.0** | −50.5 (−57%) |
| `/log` | 79.4 KB gz | **32.1** | −47.3 (−60%) |
| `/progress/volume` | 40.0 KB gz | **29.6** | −10.4 (−26%) |
| `/progress/frequency` | 40.0 KB gz | **29.6** | −10.4 (−26%) |
| `/progress/records` | 40.0 KB gz | **34.4** | −5.6 (−14%) |
| `/log/[sessionId]` | 79.4 KB gz | 79.6 | — (it genuinely uses all of it) |
| `/library`, `/settings` | 41.1 / 34.4 | unchanged | — |

**≈124 KB gz** removed across the app — more than double the audit's ~56 KB estimate.

### QW3 · The layout's awaits go out together, without breaking auth — **done**

`Promise.all([requireUser(), getActiveSession()])` looks like parallelisation and is really an
auth bug. On an expired cookie the two settle differently — `requireUser` signals with
`redirect()`, which *throws* `NEXT_REDIRECT`, while every read throws `ApiError(401)` — and
`Promise.all` adopts whichever rejects **first**. Roughly half of expired sessions would have
landed on `error.tsx` instead of Google login.

The fix is `lib/auth.parked()`: attach a no-op rejection handler to a read, hand the *original*
promise back, resolve the user, then await it. The request is already on the wire, the rejection
cannot beat the redirect, and awaiting it afterwards still throws — a genuine 500 is not
swallowed, it just can't win the race.

Applied in `(app)/layout.tsx` and `dashboard/page.tsx` (which had the same latent race in its own
`Promise.all`). Verified: signed-out and garbage-cookie requests to `/dashboard`, `/log`,
`/library` and `/settings` all still return **307 → Google**.

### QW4 · `set_count` rides along with the active session — **done**

`getSession(active.id)` existed to compute one integer and dragged every set plus full exercise
rows across the wire — a whole serial hop in the layout *and* another in the page. The count is
now computed in `services/sessions.get_active_session` (so REST and MCP stay in lockstep
automatically) and returned on `ActiveSessionOut` — **not** `SessionOut`, which is validated
straight off raw ORM rows at eight call sites and would raise on a required field with no matching
attribute.

It costs nothing to produce: `_activity()` already scanned the session's sets to decide staleness,
so it now returns `(last_touched, count)` from one aggregate.

### S1 · The MCP surface is off the REST cold path — **done**

`app/main.py` imported `app.mcp.asgi` at module scope, dragging the `mcp` SDK, `jsonschema`,
`sse_starlette` and `uvicorn` into every REST cold start. `app.services.images` and
`authlib.jose` did the same for `httpx` and the JOSE stack.

```
import app.main    before 366 ms  →  after 240 ms      (median of 5, same venv, neutral cwd)
```

The two small ones were easy — `services.images` moved inside `ensure_illustration`, and
`httpx`/`authlib` behind accessors in `app/auth/google.py`. The MCP one needed more: the session
manager's `run()` is an `anyio` task group, and a task group must be entered and exited by the
**same task**, so it cannot be opened by whichever request arrives first and closed at shutdown.
`asgi._LazyTransport` instead has the lifespan spawn one worker that parks on an event; the first
**authorized** `/mcp` request sets it, the worker enters `run()` and stays there until shutdown,
then exits cleanly. An unauthenticated probe — most of what a public endpoint receives — is
answered from the 401 path without importing anything.

Three tests hold it: a **subprocess** check that `import app.main` leaks none of the six modules
(an in-process `sys.modules` assertion would be vacuous, since other tests import the SDK
directly), one that drives the real FastAPI lifespan and asserts the runtime is unbuilt at boot,
unbuilt after an anonymous probe, and built after an authorized call, and one that a REST-only
process starts and stops without hanging on the parked worker.

### S5 · `analytics.volume` aggregates in SQL — **done**

It used to select one row per *set* and fold them in Python, so a year's range shipped thousands
of rows to produce a few dozen — cost growing with training history rather than with the answer.
Now one row per exercise. Three details were load-bearing and are in the code comments:
`coalesce` around each `sum` (an empty group is `NULL`, and `None` already means "bodyweight"
here), `bool_or(weight_kg IS NULL)` so a partial tonnage is never reported as a real total, and
**the sort stays in Python** — DB collation orders differently from Python codepoints and would
silently change MCP output.

### S6 · The desktop-only panels are Suspense-deferred — **done**

`.panel` is `display: none` below 768px, so on the screen size with a latency budget the Volume
and Frequency panels' data is never seen. Both now fetch inside a `Suspense` boundary: the phone
screen streams as soon as its own reads land.

`listPrs` deliberately stays blocking even though Records is also desktop-only — it feeds "Latest
PR" and the week's PR count above the fold, and it has no React `cache()`, so deferring it would
issue a *second* request for data the page already needs.

The lifetime `listSessions({limit: 1})` ("has this account ever logged anything?") is now asked
only when the answer is in doubt: any PR, or any session in the last nine days, settles it.

### The `??` → `||` footgun — **done**

`lib/api.ts` and `lib/env.ts` resolved their base URLs with `??`, so an env var set to the **empty
string** — an easy Vercel mistake — was honoured rather than falling back. `SERVER_API_URL = ""`
means every RSC fetch resolves against a relative base, `getMe()` fails, and the shell redirects
every signed-in page to login forever. Empty is never a URL anyone meant; both now use `||`.

*(The audit also flagged `.env.production` pinning `API_INTERNAL_URL=http://localhost:8000`. It
**does** exist — at the repo root, not under `apps/web/` where this first went looking. It is
gitignored and excluded from the Vercel upload, and Next only reads env files from the app
directory, so it never reaches a real build. But its own first line reads "Local development",
which makes the name a trap: `.env.production` is a Next.js magic filename, and one copy or
symlink into `apps/web/` would point every production RSC fetch at localhost. **Rename it** to
something inert.)*

### Net effect on one `/dashboard` render

Measured against a local stack (seeded catalog, real session cookie, warm processes — so this is
the fan-out alone, with all network cost removed):

```
BASELINE (HEAD)                          AFTER
 10 API calls, 273.7 ms API time          8 API calls, 91.5 ms API time
 all 10 blocking                          6 blocking + 2 deferred behind Suspense
 /api/sessions/{id} detail hop            gone (QW4)
 two /api/sessions (window + lifetime)    one (S6 short-circuit)
 TTFB median 44.5 ms                      TTFB median 15.5 ms
```

---

## Rejected — and two of these were the audit's own proposals

| Proposal | Why not |
|---|---|
| **S4 · `LazyMotion` on `/log/[sessionId]`** | **Measured, and it made the route bigger.** With `m` + a statically-imported `domAnimation`, the route went 79.6 → **86.0 KB gz** (+6.4). The split machinery ships on top of a feature set that is already ≈ what `motion.*` pulled for these opacity/transform animations, so nothing is dropped. The async `features={() => import(…)}` form might do better but is unsafe here: `m` applies `initial` styles regardless of features and `Sheet.tsx` has no `initial={false}`, so tapping "add exercise" before the chunk lands renders an invisible sheet over an invisible scrim. Not worth 6 KB. |
| **S2 · root `app/loading.tsx`** | **Built, measured, reverted.** It works — `<head>` and a shell flush immediately — but flushing bytes before the `(app)` layout resolves means `redirect()` can no longer be an HTTP redirect. Measured: signed-out `/dashboard` went from **307 + `Location`** to **200 with an in-band, JS-dependent redirect**. That trade made sense at a 3.6 s TTFB; at 222 ms it does not. A shared authed URL should bounce a signed-out visitor at the edge, not after a bundle download. |
| Capping `services/prs.list_prs` | A naive cap is a silent correctness regression, not a fix: the list is ordered by exercise name, and home derives "latest PR" and "PRs this week" from all of it — truncating would quietly corrupt both. Proper pagination is an API contract change across REST + MCP + generated types for a query already bounded in practice by *exercises trained × 3 metrics*. Revisit only with an `achieved_at`-ordered records feed. |
| `experimental.cssChunking: 'strict'` | A literal no-op. Its only consumer is the **webpack** config; this project builds with Turbopack. Passes validation, warns nothing, changes zero bytes. |
| `GET /api/home` aggregate, naive form | The fan-out is already `Promise.all`, so it costs `max()` not `sum()`. Running ~15 statements serially on one `AsyncSession` would now almost certainly be **slower** than 6 parallel calls at ~15 ms each. |
| `cacheComponents` / PPR | Cannot prerender a static shell *and* keep the auth gate ahead of page data. Moving `requireUser` inside a boundary makes signed-out cold loads hit `error.tsx` instead of redirecting — the same failure QW3 exists to prevent. |
| Touching `db.py` — `pool_pre_ping`, `NullPool`, `get_db_ro()` | All three were about the 1.1 s `SELECT 1`, which is now 19 ms. `pool_pre_ping` framing was 83% of DB time and is now below the noise floor. The pool was already warm (6 measured RTT vs ~9 for a fresh connection). **Leave `db.py` alone.** |

---

## What is left

Nothing on this list is urgent — together they are worth far less than any single item above.

- **Commit the region** to `apps/web/vercel.json` / `apps/api/vercel.json` so it survives a project
  rebuild instead of living only in the dashboard.
- **Add `Server-Timing`** to the FastAPI middleware (`db;dur=…, total;dur=…`) and the Next route.
  The highest-value instrumentation available here: it makes every claim in this document
  falsifiable in DevTools → Network → Timing.
- **Measure the real cold-start rate** (Vercel Observability → Functions, cold-start % per route
  over 24 h). S1 already banked 126 ms of it; this tells you what that is worth.
- **Prettier has drifted** — 8 authored files under `apps/web` fail `prettier --check` and did
  before this work. Not a performance item, but it means that gate is red. (The API suite's own
  red — three tests failing on `ChromaKeyError` — *was* fixed here: the provider stubs handed back
  placeholder bytes like `b"PNGDATA"`, which stopped decoding once the pipeline gained the chroma
  key step. `tests/_imagehelp.fake_generated_png()` now returns a real magenta-ground PNG, and a
  `style_version == "1"` assertion that had rotted through two style bumps behind that failure now
  asserts against `prompt.STYLE_VERSION`. **267 passed, 0 failed.**)

---

## How to measure

```bash
# Region, then the DB delta.
curl -sI https://api.tempo.clupai.com/api/health | grep -i x-vercel-id     # expect syd1::syd1::
for i in $(seq 1 12); do
  curl -s -m 20 -o /dev/null -w "%{time_starttransfer}\n" https://api.tempo.clupai.com/api/health
done
# Control — same function, zero DB access:
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{time_starttransfer}\n" \
    https://api.tempo.clupai.com/.well-known/oauth-authorization-server
done
# (health − well-known) / 6 == your function↔Neon RTT.
```

```bash
# Python import cost. Run from a neutral cwd against an explicit tree, or `app` resolves from `.`
# and you will measure the same code twice (this is easy to get wrong):
cd /tmp && DATABASE_URL=postgresql://x@localhost/x DATABASE_URL_UNPOOLED=postgresql://x@localhost/x \
  PYTHONPATH=<repo>/apps/api <repo>/apps/api/.venv/bin/python -W ignore \
  -c 'import time; t=time.perf_counter(); import app.main; print(f"{(time.perf_counter()-t)*1000:.0f} ms")'
# Attribution:
cd apps/api && uv run python -X importtime -c 'import app.main' 2>&1 | sort -t'|' -k2 -rn | head -20
```

```bash
# Per-route client JS from the real manifests — Turbopack prints no size table, so `next build`
# output is useless for this. Compare two trees; absolute numbers move with Next versions.
cd apps/web && pnpm build
for r in "(app)/dashboard" "(app)/log" "(app)/log/[sessionId]" "(app)/library"; do
  p=".next/server/app/$r/page_client-reference-manifest.js"; total=0
  for c in $(grep -o 'static/chunks/[a-zA-Z0-9_/.-]*\.js' "$p" | sort -u); do
    [ -f ".next/$c" ] && total=$((total + $(gzip -9 -c ".next/$c" | wc -c | tr -d ' ')))
  done
  printf "%-26s %8.1f KB gz\n" "$r" "$(echo "scale=1; $total/1024" | bc)"
done
```

To count API calls per render, run the API with `--log-level warning` to a file (it logs one JSON
line per request), render the page **twice** — the first warms both processes — and read the lines
after the warm-up. Do not truncate the log with `: >` while uvicorn holds it open: the process
keeps writing at its old offset and you will silently lose the first requests.

Lighthouse cannot authenticate — run it against a preview deployment and drive an authed session
with a cookie, or accept that `/` only proves the asset story.

---

## Open questions

| Question | How to settle it |
|---|---|
| Is the 9.58 s first request Neon compute resume? Python cold start cannot explain the 8.2 s gap against a 1.41 s warm request. | Neon Console → Monitoring → look for a compute-suspend/resume event at that timestamp. If so, raise the suspend timeout. |
| What is the real cold-start rate? | Vercel Observability → Functions → cold-start % per route over 24 h. |
| Real-device hydration cost | DevTools Performance, 4× CPU throttle, on `/dashboard` and `/log/[sessionId]`. |
