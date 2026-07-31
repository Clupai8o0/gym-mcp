# HANDOVER — Phase 11: mobile-first shell, dashboard-as-home, PWA hardening

> **For the executor session.** You are picking this up cold. Read this file top to bottom
> before writing code. It supersedes nothing in `docs/` — the locked decisions, guardrails,
> and conventions in [`../CLAUDE.md`](../CLAUDE.md), [`08-design-motion-system.md`](./08-design-motion-system.md),
> and [`12-conventions.md`](./12-conventions.md) all still bind.
>
> Written 31 Jul 2026, from `phase-9-polish` @ `495b5de`.

---

## 0. Where things stand

Phases 0–9 are built and self-verified; **none are merged to `main`** — each branch is cut
from the previous one's HEAD. `phase-9-polish` is the tip. `docs/STATUS.md` is the live
tracker and is accurate.

The app **runs locally** (see §1) and was driven end to end this session: 873 exercises
seeded, a workout logged through the UI, PRs detected, dashboard/skills/settings all
rendering against real Postgres. What follows is grounded in that run, not in the plan.

**Still blocked on external prereqs** (not your problem, don't try to work around them):
Neon, Google OIDC client, OpenAI key, Blob token, and the **human security sign-off on
Phase 3** which gates production deploy.

---

## 1. Getting it running (verified this session)

Local Postgres 16 stands in for Neon. Everything below was executed and worked.

```bash
createdb tempo_dev
```

Create `.env` in the repo root (it is gitignored). Only the two DB URLs are required —
every other setting has a local dev default in `app/core/config.py`:

```
DATABASE_URL=postgresql://<you>@localhost:5432/tempo_dev
DATABASE_URL_UNPOOLED=postgresql://<you>@localhost:5432/tempo_dev
PUBLIC_BASE_URL=http://localhost:8000
OAUTH_ISSUER=http://localhost:8000
WEB_ORIGIN=http://localhost:3000
SESSION_COOKIE_DOMAIN=
SESSION_SIGNING_KEY=<openssl rand -hex 32>
TOKEN_HASH_PEPPER=<openssl rand -hex 32>
NEXT_PUBLIC_API_URL=http://localhost:8000
API_INTERNAL_URL=http://localhost:8000
NEXT_PUBLIC_BASE_URL=http://localhost:3000
```

**Gotcha:** pydantic-settings resolves `env_file=".env"` **relative to the current working
directory**, so a single root `.env` is not enough. Symlink it (all gitignored):

```bash
ln -sf ../../.env apps/api/.env
ln -sf ../../.env apps/web/.env
ln -sf ../.env    scripts/.env
```

Then:

```bash
cd apps/api  && uv run alembic upgrade head          # 3 migrations
cd scripts   && uv run python seed_catalog.py        # -> inserted=873
cd apps/api  && uv run uvicorn app.main:app --port 8000
cd apps/web  && pnpm dev                             # :3000
```

**Auth bypass.** Google OIDC is not provisioned, so there is no login. Mint a session
cookie with the app's own `app/auth/session.py` (`issue_session_token(user_id)` +
`SESSION_COOKIE`), then set it in the browser at `localhost:3000`:

```js
document.cookie = "tempo_session=<token>; path=/"
```

Cookies ignore port, so `:8000` accepts it too. This is a **local dev shim only** — do not
add a bypass route to the app.

---

## 2. What you are building

**Run all four phases in one go. Do not stop for review between them.** Work through
11A → 11B → 11C → 11D and report once at the end.

They are strictly ordered, and the ordering is a real dependency, not a checkpoint: **do not
start a phase until the previous one's acceptance criteria actually pass.** 11B and 11C both
read the session state introduced in 11A. "Green" here means the checklist is demonstrably
met by tests and a manual check — it does not mean a human has looked at it.

If a phase's criteria cannot be met, **stop there** and report what blocked you rather than
building the next phase on a broken foundation.

The visual target is an interactive proposal with mockups at real device size:
**https://claude.ai/code/artifact/659b2799-c852-40cd-bb4a-b3d0f14c998b**
(Nav option **A**, dashboard concept **A** — those are the approved ones. Ignore B and C,
they are documented alternatives.)

### The governing constraint

**One screen, no scrolling, on a phone.** Budget against a 393×852 device:
**759 px** installed to the home screen, **~690 px** in Safari with chrome showing. Design
to 690. The approved home screen lands at ~542 px of content, so you have slack — spend it
on breathing room, not more content.

Every layout decision below is downstream of that number. If something does not fit, it
moves one layer down; nothing gets deleted.

---

## Phase 11A — Give a workout a lifecycle

**Branch:** `phase-11a-session-lifecycle` from `phase-9-polish`.

Today a session has `performed_at` and a nullable `duration_minutes` and nothing else.
"Is a workout in progress?" is answered by `isToday(performed_at)` **inside a server
component**, so it evaluates in the server's timezone — UTC in production. Two consequences
observed in the running app:

- Train at 5 pm in UTC−8 and your session is already "tomorrow" in UTC: no Continue card,
  and you start a second session on top of the first.
- A workout you finished at 7 am still reads **"In progress"** at 11 pm, and yesterday's can
  never be reopened from `/log`.
- `duration_minutes` renders on the recent-workouts list but **nothing ever writes it**.

Everything in 11B and 11C leans on this being fixed properly.

**Scope**

- **Migration `0004`** — add `workout_sessions.ended_at TIMESTAMPTZ NULL`. Additive, no
  backfill needed (existing rows read as never-finished; see the note below). Keep it
  reversible and idempotent.
- **`services/sessions`**
  - `finish_session(db, user_id, session_id)` — stamps `ended_at`, computes and stores
    `duration_minutes` from `performed_at`. Idempotent: finishing a finished session is a
    no-op, not a 409.
  - `get_active_session(db, user_id)` — the most recent session with `ended_at IS NULL`.
    **This replaces the date heuristic entirely.** No timezone logic anywhere.
  - Decide and document: should starting a new session auto-finish a dangling one? A
    session left open for three days is the obvious failure mode. Recommendation: auto-finish
    anything older than ~12 h on read, stamping `ended_at` from the last set's timestamp.
    Log the decision in `01`'s Decision Log either way.
- **REST** — `POST /api/sessions/{id}/finish` and `GET /api/sessions/active`. Thin adapters.
- **MCP** — `finish_session` and `get_active_session` tools. ⚠️ **Non-negotiable guardrail:**
  REST and MCP stay in lockstep, both calling the same `services/` function. The contract
  suite in `tests/mcp/test_mcp_contract.py` enforces it — extend it, don't work around it.
- **Frontend** — `/log` uses `getActiveSession()` instead of `items.find(isToday(...))`.
  Add a **Finish workout** action to the session logger.

**Acceptance criteria**

- [ ] `alembic upgrade head` → `ended_at` present; `downgrade base` clean; re-upgrade repeatable; `alembic check` reports no drift.
- [ ] `uv run pytest -q` green, **+ new tests**: finish stamps duration, finish is idempotent, active-session resolution, the dangling-session rule, cross-user scoping (you cannot finish someone else's session).
- [ ] MCP↔REST contract test covers both new tools.
- [ ] Architecture guard still passes (no DB access in routers or MCP adapters).
- [ ] `ruff` + `black --check` + `mypy --strict` clean.
- [ ] **Manually verified against local Postgres:** start a session, finish it, confirm `/log` no longer shows it as active and `duration_minutes` is populated.
- [ ] No `isToday` call survives in any server component.

---

## Phase 11B — New app shell: bottom tabs + docked session bar

**Branch:** `phase-11b-mobile-shell` from 11A.

Replaces the desktop header. Pure frontend — no API change.

**Scope**

- **`TabBar`** — bottom, four labelled tabs: **Home · Library · Log · You**.
  - Icons **and** labels. Do not ship icon-only.
  - `Log` is a **state, not a destination**: idle it is a normal tab; with an active session
    it takes `--accent` and shows a dot badge.
  - `You` holds Settings (units, connected apps, account, install card).
  - Respect `env(safe-area-inset-bottom)`. `viewportFit: cover` is already set in
    `app/layout.tsx` — don't re-add it.
- **`SessionBar`** — docked directly above the tab bar on **every** screen while a session is
  active. Shows title · set count · elapsed. Tap → `/log/[id]`. Driven by
  `get_active_session` from 11A, never by a date.
- **Top chrome** — the sticky `AppHeader` goes away on mobile. Each screen gets a compact
  title row that scrolls with content. Keep the offline chip and the skip link.
- **Desktop (≥768 px)** — the tab bar becomes a **left rail**. Same components, different
  composition. Do not build a second set of components.
- **Retire** `AppHeader` / `AppNav` / `UserMenu` as they exist. Sign-out moves into the
  account card under `You` — it should not be a permanently visible destructive control one
  thumb-width from the nav.
- **Fix while you're in here:** `lib/format.ts:68` `formatDate` uses
  `toLocaleDateString(undefined, …)`. The server formats in its locale and the browser in
  the user's, which produces a **live hydration error on `/settings`** (`AccountCard`,
  "Member since") that regenerates the whole authed subtree on the client. Pin the locale or
  format once server-side and pass the string.

**Acceptance criteria**

- [ ] `next build`, `eslint .`, `tsc --noEmit` all clean.
- [ ] At 393×759 the tab bar and session bar are visible **without scrolling** on every authed route.
- [ ] Session bar appears on Library/Home/You while a session is live, and disappears on finish.
- [ ] **Zero console errors or hydration warnings** on `/`, `/library`, `/log`, `/dashboard`, `/dashboard/skills`, `/settings` — verify by loading each. The `/settings` hydration error above must be gone.
- [ ] Keyboard walk-through: skip link → tabs → content, all focus states visible.
- [ ] Reduced-motion honoured; tokens-only styling (no hardcoded hex/px/ms).
- [ ] ≥768 px renders the left rail, not a stretched tab bar.

---

## Phase 11C — Dashboard becomes home

**Branch:** `phase-11c-dashboard-home` from 11B.

**Scope**

- **`/dashboard` becomes the summary screen** (concept A in the artifact), top to bottom:
  1. Compact date + avatar row
  2. **Active session card** (or, if none, a Start affordance) — the workout must never be below the fold
  3. Four stats for *this week*: Sessions · Tonnage · Sets · PRs
  4. Seven-day strip
  5. One row: latest PR
  6. One row: top skill
- **Move the existing sections out**, largely as-built — they already have their loading and
  empty states:
  - `/progress/volume` ← today's `VolumeChart` **plus the `RangeControl`**
  - `/progress/frequency` ← `FrequencyHeatmap` at a readable cell size
  - `/progress/records` ← `PrList`
  - `/progress/skills` ← `SkillsBoard` (retire the `DashboardTabs` sub-nav)
- **The range control moves with volume.** It currently sits above the records grid but
  records are all-time — `listPrs()` takes no window — so it reads as broken. Below 768 px
  home shows no range control at all; home is always "this week" + all-time PRs.
- **Front door** — `lib/auth.ts` `loginUrl()` defaults to `/library`; the logo links there
  too. Both become `/dashboard`. Also `manifest.webmanifest` `start_url: "/log"` →
  `"/dashboard"`, and re-order `shortcuts` to match.
- **Empty state — the one genuinely new screen.** A brand-new account currently lands on
  three empty boxes, and that is now the first impression. Replace with: one line of
  welcome, *Start your first workout*, *Browse 873 exercises*. Stats appear once there is
  something to count.
- **Desktop** — above 768 px the `/progress/*` content renders **inline** in the right
  column rather than as separate destinations. The vertical budget that forced the split
  does not exist there.

**Decide before you build the PR row** — a product call, not a bug:
observed in the running app, three sets of an ascending warm-up (80×8, 90×6, 102.5×3) all
came back `is_pr=true, type=weight`. Three celebration chips in one exercise block. The
"signature moment" fires on every set of a normal ramp. Related: `_detect` in
`app/services/sets.py:129` returns on the **first** matching metric, so a set that is both
heaviest *and* highest-rep only ever records the weight — `/api/prs` held one row despite 8
reps being logged. Options: compare against the *previous session's* best rather than the
previous set, or record all qualifying metrics per set. **Ask the orchestrator before
changing PR semantics** — it is a locked contract ported from the legacy app.

**Acceptance criteria**

- [ ] Home fits **690 px** at 393 px wide with no scroll, populated *and* empty.
- [ ] Every moved section works at its new route with loading + empty states intact.
- [ ] Range control governs the whole `/progress/volume` page.
- [ ] Sign-in lands on `/dashboard`; `start_url` matches.
- [ ] New-account empty state renders (test with a fresh user row).
- [ ] Build/lint/typecheck clean; no hydration warnings.

---

## Phase 11D — PWA cache privacy fix

**Branch:** `phase-11d-pwa-cache` from 11C. Small, self-contained, high priority.

**The PWA itself is already done and verified** — SW registers and controls, manifest
complete, all seven icons at correct dimensions, `/offline` page, install card, safe areas.
Installability criteria are met. **Do not rebuild any of it.**

**But there is a live privacy bug.** `public/sw.js` caches navigations per URL, and
authenticated pages are server-rendered HTML containing all the user's data. Reproduced this
session: visit `/dashboard`, `/settings`, `/library` signed in → clear cookies → go offline →
navigate to `/dashboard` → **the previous user's full dashboard renders from cache**, name
and records included. The SW's own header comment claims "authenticated data is never served
stale from cache"; that is true of API responses only. Nothing calls `caches.delete()` on
sign-out, so it persists indefinitely. On a shared or family device, that is your training
data shown to the next person.

**Scope**

- Do **not** cache authed navigations. Precache `/offline` and public routes only; an offline
  revisit of an authed route falls through to `/offline`.
- Clear caches on sign-out (defence in depth) from the account card's sign-out handler.
- Bump the cache version to `v3` so existing clients evict.
- Correct the misleading comment at the top of `sw.js`.

**Acceptance criteria**

- [ ] After sign-out + offline, no authed route renders cached content — `/offline` is served.
- [ ] `caches.keys()` contains no authed page URLs after visiting them.
- [ ] Offline shell still works: install, go offline, navigate → `/offline` renders.
- [ ] Set-logging offline queue (`lib/offline`) is **untouched** and still functions.

---

## 3. Explicitly out of scope

Do not do these. Flag them and stop if they seem necessary.

- Any change to OAuth issuance, PKCE, token rotation, or the AS tables — **Phase 3 is
  awaiting human security sign-off**; touching it invalidates that review.
- Deploying anything, or provisioning Neon / Google / OpenAI / Blob.
- Teams, billing, social, nutrition — the standing non-goals.
- Rebuilding the PWA, the service worker's offline queue, or the design tokens.
- Renumbering or restructuring `docs/10-execution-plan.md`.

## 4. Adjacent findings — do only if the orchestrator says so

Each is small and each is mostly-written code missing a caller. They are **not** in the
scope above:

| | Finding | Where |
|---|---|---|
| 5 | A set can be deleted but not edited; `updateSet()` is typed, tested, never called | `components/log/SetRow.tsx`, `lib/client.ts:120` |
| 6 | Workout title is a one-shot at creation; `updateSession()` also unused | `lib/client.ts:104` |
| 7 | No custom-exercise UI — chat has `create_custom_exercise`, the app has nothing | `components/log/ExercisePicker.tsx` |
| 8 | Nothing calls `POST /api/exercises/{id}/illustration`, so pending art never resolves | `components/library/IllustrationImage.tsx` |
| — | Offline queue covers `log_set` only; starting a session and catalog search both need network | `lib/offline/queue.ts` |
| 4 | "Browse the library" on the marketing page bounces signed-out visitors to Google | `app/(marketing)/page.tsx:62` |

## 5. Working agreement

Per [`11-agent-workflow.md`](./11-agent-workflow.md): **one phase = one branch = one PR**,
with the acceptance checklist ticked and evidence in the description. Keep that structure
even though you are running straight through — four branches chained off each other
(`phase-11a-…` → `phase-11b-…` → `phase-11c-…` → `phase-11d-…`), four PRs, exactly as
Phases 0–9 were cut. Update [`STATUS.md`](./STATUS.md) as you finish each phase — scope, DoD
evidence, decisions — rather than all at the end. Log any decision that changes a locked
choice in `01`'s Decision Log.

Phases 11B and 11C are UI, so they carry the **Antigravity frontend-review gate** against
`apps/web/FRONTEND_REVIEW.md` and `docs/08` — same as Phases 6–9, and still outstanding for
those. You are not expected to pause for it mid-run: **record it as outstanding in `STATUS.md`
and carry on**, the way the earlier UI phases did. The same applies to the live-authed-render
and Lighthouse checks, which need a deploy.

**Report once, at the end**, covering all four phases: what shipped, DoD evidence per phase,
decisions taken, gates still outstanding, and anything you deliberately left undone.

Conventional Commits. Python: ruff + black + mypy strict, async throughout. TS: eslint +
prettier, strict, **no `any` at the API boundary** — regenerate `lib/api-types.ts` with
`pnpm gen:api` after any schema change in 11A.

## 6. Reference

- Layout proposal with mockups — https://claude.ai/code/artifact/659b2799-c852-40cd-bb4a-b3d0f14c998b
- Flow walkthrough + full findings list — https://claude.ai/code/artifact/a3d97ce9-bee7-4834-8f54-8731161cdf98
- Interactive demo of current behaviour — https://claude.ai/code/artifact/0e56f722-ca72-483a-adcc-ed075dd7651b
