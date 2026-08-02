# 13 — Performance: why the app is slow, and the plan to fix it

Audited **2026-08-02** against production, by two independent passes: a 36-agent sweep whose
findings were adversarially verified (17 of 28 survived), and a separate Codex CLI audit run
read-only over the worktree. Where they disagreed, the disagreement is recorded below rather than
smoothed over.

Numbers marked **[measured]** were taken first-hand. Everything else is labelled an estimate.

---

## The diagnosis

**The functions run in Virginia. The database is in Sydney.**

```
x-vercel-id: syd1::iad1::…        ← both tempo-web and tempo-api          [measured]
Neon host:   …ap-southeast-2.aws.neon.tech   (54 ms TCP from Sydney)      [measured]
```

A request from Australia enters the Sydney edge, is shipped to `iad1` to execute, and reaches back
across the Pacific to a database that was 54 ms from the user all along.

One query is not one crossing:

```
GET /.well-known/oauth-authorization-server   0.318 s   ← same function, no DB   [measured]
GET /api/health          (one SELECT 1)       1.33 / 1.35 / 1.57 s               [measured]
                                              ───────
                        ≈ 1.0–1.25 s to run one SELECT 1
```

Divided by the ~185 ms iad1↔ap-southeast-2 RTT, that is **six round trips**, which decomposes
exactly: `pool_pre_ping` (BEGIN + `;` + ROLLBACK = 3) + transaction BEGIN + the query itself +
`get_db`'s unconditional COMMIT. **Five of the six are framing. One is work.**

Then multiply. A single authenticated home render issues **ten API calls** — captured from the
API's own request log, on localhost with a warm process and a local DB, so this is the fan-out
alone with all network cost removed:

```
GET /api/me                    22.87 ms     GET /api/sessions        28.04 ms
GET /api/sessions/active       23.17 ms     GET /api/sessions        28.85 ms
GET /api/analytics/frequency   16.50 ms     GET /api/skills          20.59 ms
GET /api/analytics/volume      26.26 ms     GET /api/exercises        3.19 ms
GET /api/prs                   19.86 ms
GET /api/analytics/volume      19.29 ms   → 10 calls, 208.6 ms       [measured]
```

Counting statements rather than wall-clock, the Codex pass reached the same place from the other
direction: **≈36 DB protocol exchanges** per dashboard render — 16 business SQL + 10 `pool_pre_ping`
+ 10 `COMMIT`. Two methods, one conclusion.

And they are not one wave. `app/(app)/layout.tsx` awaits `requireUser()` → `getActiveSession()` →
`getSession()` **sequentially** before the page's `Promise.all` resolves. `GET /dashboard` — which
does nothing but resolve the session and redirect — measures **1.15 s TTFB** [measured].

### Cold home-page budget

| Stage | Today | After region pin |
|---|---:|---:|
| DNS + TCP + TLS → syd1 edge | 80 ms | 80 ms |
| syd1 edge → web function | 100 ms | ~5 ms |
| Next.js cold start | 0–400 ms | 0–400 ms |
| Layout hop 1 — `/api/me` | 1,150 ms | 75 ms |
| Layout hop 2 — `/api/sessions/active` (serial, no data dependency) | 1,150 ms | 75 ms |
| Layout hop 3 — `getSession()`, only mid-workout | +1,480 ms | +85 ms |
| Page fan-out (7 parallel; cost = slowest) | 1,350 ms | 90 ms |
| Python cold start, first call only | +800–1,500 ms *(est)* | same |
| **TTFB** | **≈3,650 ms** | **≈340 ms** |
| Fonts 71.5 KB + CSS 14.0 KB gz + entry JS ~90 KB gz | 200 ms / 1,500 ms slow-4G | same |
| Hydration | 30 ms desktop / 130 ms mid-tier Android *(est)* | same |
| **Interactive, warm, broadband** | **≈4.0 s** | **≈0.6 s** |

The first request of a session measured **9.58 s** against 1.41 s warm [measured]. Python cold
start alone cannot explain an 8.2 s gap; Neon compute resume is the likely remainder — see
Open questions.

---

## The plan

### Quick wins — do first

**QW1 · Pin both Vercel projects to `syd1`.** ~3.3 s off the front door. Effort **S**.

Two files, one key each:

```json
{ "$schema": "https://openapi.vercel.sh/vercel.json", "regions": ["syd1"] }
```

in `apps/web/vercel.json` and `apps/api/vercel.json`. **Flip Settings → Functions → Function Region
to Sydney in the dashboard first** — it captures the entire win, is one click, and is instantly
reversible. Commit the files after it is proven.

> **Do not** reach for `vercel.ts` here, despite this repo's preference for it in `09`.
> `@vercel/config` is not installed and is absent from `pnpm-lock.yaml` [verified]; adding it puts a
> lockfile change on the deploy path, and Vercel installs frozen. Plain `vercel.json` is identical
> in effect. Update `09` rather than take the risk.

Acceptance: `x-vercel-id` reads `syd1::syd1::…` and `/api/health` median drops under 100 ms.

**QW2 · Deep-import `@/components/log`.** ~48 KB gz off `/dashboard` and `/log`. Effort **S**.

The `motion` chunk (126,552 raw / 41,641 gz) rides the barrel onto routes that never animate.
Change `components/home/WorkoutCard.tsx`, `components/home/HomeWelcome.tsx` and
`app/(app)/log/page.tsx` to import `@/components/log/SessionStarter` directly. Leave
`log/[sessionId]/page.tsx` on the barrel — it genuinely renders `SessionLogger`. Add an
ESLint `no-restricted-imports` guard on the exact group `@/components/log`.

Per-route JS today [measured]: `/dashboard` 223.5 KB gz / 194.2 br · `/log` 214.1 / 185.8 ·
`/library` 174.7 / 151.2 · `/settings` 167.8 / 145.0.

**QW3 · Parallelise the two independent layout awaits.** One full serial hop. Effort **S**.

⚠️ **`Promise.all([requireUser(), getActiveSession()])` is an auth bug, not a fix.** `requireUser`
signals with `redirect()` (throws `NEXT_REDIRECT`); `getActiveSession` throws `ApiError(401)`.
`Promise.all` adopts whichever rejects first, so roughly half of expired sessions would land on
`global-error.tsx` instead of Google login. Start both, then resolve auth first:

```ts
const mePromise = getMe();
const activePromise = getActiveSession().catch(() => null);
const me = await mePromise;
if (!me) redirect(loginUrl());
const active = await activePromise;
```

The same latent race already exists in `dashboard/page.tsx` and the `progress/*` pages; it is dead
code only because the layout redirects first. Parallelising un-masks it — fix them together or keep
`requireUser()` first in each page's `Promise.all`.

**QW4 · Put `set_count` on `ActiveSessionOut`; delete the third layout hop.** Effort **S**.

`getSession(active.id)` exists to compute one integer and drags every set plus full exercise rows
across the wire. Add the count to `ActiveSessionOut` — **not** `SessionOut`, which is validated
straight off raw ORM rows at eight call sites across REST *and* MCP and would raise
`ValidationError` on a required field with no matching attribute. Compute it in
`services/sessions.get_active_session` so REST and MCP stay in lockstep automatically.

### Structural

**S1 · Make the MCP surface lazy on the REST cold path.** ~96–115 ms of cold import. Effort **M**.

`app/main.py:33` imports `app.mcp.asgi` at module scope, dragging in the `mcp` SDK, `jsonschema`,
`sse_starlette` and `uvicorn` on every REST cold start. Measured breakdown of `import app.main`
(452 ms total, 1041 modules) [measured]:

| module | cost | needed by a REST request? |
|---|---:|---|
| `app.mcp.asgi` | ~85–96 ms | no — only `/mcp` |
| `app.services.images` → `app.images.blob` → `httpx` | ~17–19 ms | no — only illustration generation |
| `authlib.jose` | ~14–17 ms | no — only the Google callback |

The two small ones are nearly free: move `app.services.images` inside `ensure_illustration`
(`routers/exercises.py`) and the authlib/httpx imports inside the login/callback handlers
(`app/auth/google.py`). The MCP one needs a lazy ASGI shim wrapped in `Route("/mcp", …)` to preserve
the exact-path/no-redirect property claude.ai depends on, plus an MCP-free lifespan holding an
`AsyncExitStack`. Add a test asserting `"mcp" not in sys.modules` after `import app.main`, or a
stray future import silently undoes it.

Do **not** also add an `@lru_cache get_mcp()` factory — the whole module body of `app/mcp/server.py`
is 13.5–17.6 ms against ~100 ms for the SDK import, so it saves nothing once the import is deferred,
and it breaks the lockstep contract suite `CLAUDE.md` names as a guardrail.

**S2 · Add `loading.tsx` at the ROOT segment**, not `app/(app)/`. Effort **S**.

Both audits landed here independently — one from `next/dist/client/components/layout-router.js`,
the other from the installed docs (`layout.md:316`): a loading boundary below an uncached layout
cannot display until that layout finishes. `app/(app)/loading.tsx` wraps the layout's *children*
and cannot unblock the layout's own awaits. `app/layout.tsx` is synchronous, so `app/loading.tsx`
streams the whole `(app)` subtree while `<head>` flushes. Give it a minimal shell, not a spinner.

**S3 · Trim the `@/components/dashboard` barrel.** ~8.4 KB gz on `/progress/volume` and
`/progress/frequency`. Effort **S**. Most of the win is the `next/image` cluster pulled in via
`PrList` → `IllustrationImage`, not the skills components.

**S4 · `LazyMotion` on `/log/[sessionId]`**, which still ships all 41.6 KB gz — 51% of that route's
client JS. Effort **M**.

⚠️ The import form matters and the two audits conflicted; resolved by running it [verified]:

```
motion/react-m  → 165 exports, has 'm'? false, has 'div'? true   (tag names, no m namespace)
motion/react    → has 'm'? true, LazyMotion? true, domAnimation? true
```

The entrypoint exists but there is no `m` to destructure. Use
`import { m, LazyMotion, domAnimation } from "motion/react"`, mount `<LazyMotion features={domAnimation} strict>`
once in the `(app)` layout with `domAnimation` **statically** imported. The async
`features={() => import(...)}` form is unsafe here: `m` applies `initial` styles regardless of
features, and `Sheet.tsx` has no `initial={false}` — tapping "add exercise" before the chunk lands
renders an invisible sheet over an invisible scrim.

**S5 · Aggregate `analytics.volume` in SQL.** Caps unbounded growth; ~nothing user-visible today.

If done, three details are load-bearing: `func.coalesce(func.sum(...), 0)` — a bare `sum()` returns
`None` for a weighted hold with no reps, and `None` is this API's signal for "bodyweight"; wrap in
`round(float(...), 3)` for `mypy --strict`; and **keep the Python sort** — DB collation orders
differently from Python codepoints, which would silently change MCP output.

Separately, cap `services/prs.list_prs` — it is unbounded, joins `Exercise`, and sits above the fold.

**S6 · Suspense-defer the two desktop-only dashboard panels.** 7 → 5 blocking calls.

Only `getVolume(range)` and `getFrequency` qualify — they feed `.panel`, which is `display: none`
below 768px. `getSkillsOverview()` does **not**: it feeds the "Top skill" row in `.highlights`,
which is mobile-visible above the fold. Extracting `PrList` is a regression, not a fix — `listPrs`
has no React `cache()`, so it would issue a second request for data already needed above the fold.

Cheaper adjacent win: `listSessions({ limit: 1 })` answers "has this account ever logged anything"
and is only consulted when the account looks empty — fetch it lazily inside that branch and remove
a fifth blocking call for every returning user.

### Rejected — do not ship these

| Proposal | Why not |
|---|---|
| `experimental.cssChunking: 'strict'` | A literal no-op. Its only consumer is the **webpack** config; this project builds with Turbopack. Passes validation, warns nothing, changes zero bytes. |
| `GET /api/home` aggregate, naive form | The fan-out is already `Promise.all`, so it costs `max()` not `sum()`. Running ~15 statements serially on one `AsyncSession` could be **slower**. A properly aggregated version (4–5 statements, target 2 calls / 8–12 exchanges) is worth revisiting **after** QW1. |
| `cacheComponents` / PPR | Cannot prerender a static shell *and* keep the auth gate ahead of page data. Moving `requireUser` inside a boundary makes signed-out cold loads hit `error.tsx` instead of redirecting. |
| `NullPool` / elastic concurrency | The pool is already warm. A fresh connection per request would be ~9 RTT (TCP + TLS + SCRAM) ≈ 1.66 s; measured is 1.105 s = 6 RTT. |
| `get_db_ro()` on an AUTOCOMMIT engine | Worth ~740 ms/call today, ~8 ms after QW1. Only pursue if QW1 is blocked. |

---

## A loaded footgun

`.env.production` sets `API_INTERNAL_URL=http://localhost:8000` (also `NEXT_PUBLIC_API_URL`,
`NEXT_PUBLIC_BASE_URL`), and `lib/api.ts:37` uses it for **every** RSC fetch. Production clearly
overrides it or nothing would work, but the file is a trap. Also change `??` to `||` on that line:
`??` is nullish-coalescing, so an empty-string env var yields `SERVER_API_URL = ""` and redirects
every authenticated page to login forever.

---

## How to measure

Baseline **before** touching anything:

```bash
# The headline. Region, then the DB delta.
curl -sI https://api.tempo.clupai.com/api/health | grep -i x-vercel-id     # expect syd1::iad1::
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
# Python import cost, before and after S1:
cd apps/api && uv run python -X importtime -c 'import app.main' 2>&1 | sort -t'|' -k2 -rn | head -20
```

```bash
# Per-route JS from the real manifests — Turbopack prints no size table, so `next build` output
# is useless for this.
cd apps/web && pnpm build
for r in "(app)/dashboard" "(app)/log" "(app)/library"; do
  p=".next/server/app/$r/page_client-reference-manifest.js"
  echo "== $r"
  grep -o 'static/chunks/[a-zA-Z0-9_-]*\.js' "$p" | sort -u | while read c; do
    printf "  %-24s %7s raw %7s gz\n" "$(basename $c)" \
      "$(stat -f%z .next/$c)" "$(gzip -9 -c .next/$c | wc -c | tr -d ' ')"
  done
done
```

**Add `Server-Timing`** to the FastAPI middleware (`db;dur=…, total;dur=…`) and to the Next route.
It is the highest-value instrumentation available here, because it makes every claim in this
document falsifiable in DevTools' Network → Timing panel.

Lighthouse cannot authenticate — run it against a preview deployment and drive an authed session
with a cookie, or accept that `/` only proves the asset story.

---

## Open questions

| Question | How to settle it |
|---|---|
| Is the 9.58 s first request Neon compute resume? 8.2 s is unaccounted for. | Neon Console → Monitoring → look for a compute-suspend/resume event at that timestamp. If so, raise the suspend timeout. |
| Is `syd1` selectable on this plan? | Settings → Functions → Function Region. Region availability is plan-gated. This is why QW1 says toggle before committing files. |
| What is the real cold-start rate? | Vercel Observability → Functions → cold-start % per route over 24h. If under 2%, S1 drops below the quick wins. |
| What is `API_INTERNAL_URL` actually set to in production? | `vercel env pull` in `apps/web`, inspect, delete. |
| Does the pool really survive between invocations? | The 6-RTT arithmetic says yes but it is inference from wall-clock. Set `echo_pool="debug"` and look for `"Connection %s is fresh, skipping pre-ping"` — it fires **iff** the connection is new. Settle this *before* anyone edits `db.py`. |
| Real-device hydration cost | DevTools Performance, 4× CPU throttle, on `/dashboard` and `/log/[sessionId]`. |
