# 07 — Frontend (Next.js)

One unified app with three surfaces — **Library**, **Log**, **Dashboard** — plus auth and
settings. Next.js App Router, React Server Components by default, client components only where
interaction/motion demands it. Design + motion details live in `08-design-motion-system.md`;
this doc is structure, routing, and data flow.

## App structure

```
apps/web/
├── app/
│   ├── (marketing)/
│   │   └── page.tsx              # landing / signed-out home
│   ├── (app)/                    # authenticated shell (redirects to login if no session)
│   │   ├── layout.tsx            # app chrome: bottom tabs / left rail + docked session bar (11B)
│   │   ├── library/
│   │   │   ├── page.tsx          # catalog grid: search + filters
│   │   │   └── [slug]/page.tsx   # exercise detail: illustration + how-to + PRs
│   │   ├── log/
│   │   │   ├── page.tsx          # today / active session
│   │   │   └── [sessionId]/page.tsx
│   │   ├── dashboard/page.tsx    # HOME (11C): active workout, week stats, day strip, highlights
│   │   ├── progress/             # the sections home summarises (11C)
│   │   │   ├── volume/page.tsx   # VolumeChart + the range control
│   │   │   ├── frequency/page.tsx
│   │   │   ├── records/page.tsx  # all-time PRs (no range control)
│   │   │   └── skills/page.tsx   # secondary skill-tree module
│   │   └── settings/page.tsx     # units, connected apps (MCP), account
│   ├── layout.tsx                # root: fonts, theme, providers
│   └── globals.css               # design tokens (from 08)
├── components/
│   ├── ui/                       # x.ai design-system wrappers (Button, Card, Input, ...)
│   ├── library/                  # ExerciseCard, FilterBar, MuscleTag, IllustrationImage
│   ├── log/                      # SetRow, SetEntryPad, ExercisePicker, RestTimer
│   ├── dashboard/                # PRList, VolumeChart, FrequencyHeatmap, SkillRing
│   ├── home/                     # HomeHeader, WorkoutCard, WeekStats, DayStrip (11C)
│   ├── app/                      # TabBar (tabs / left rail), SessionBar, Logo (11B)
│   └── motion/                   # shared motion primitives (see 08)
├── lib/
│   ├── api.ts                    # typed fetch client → api.tempo.clupai.com (CORS + credentials)
│   ├── auth.ts                   # session helpers (read cookie server-side)
│   └── format.ts                 # kg/lb + time formatting
├── design/                       # tokens.css, motion.ts, easings.ts
├── public/                       # icons, manifest, offline assets
└── vercel.ts                     # headers/CSP (see 09)
```

## The three surfaces

### Library
- **Grid** of `ExerciseCard`s (illustration, name, primary muscle, equipment). Server-rendered
  list; client-side instant filtering.
- **Filters:** search (name, trigram), muscle, equipment, category, level. Reflect filter state
  in the URL (`?muscle=chest&equipment=barbell`) for shareability + back-button.
- **Detail** (`[slug]`): large illustration, ordered instructions, target muscles, the user's
  PRs and recent sets for this exercise, and a "Log this" affordance that jumps to Log.
- **Placeholder state** for exercises whose `illustration_status !== 'ready'`: a tasteful
  line-art skeleton; optionally trigger on-demand generation (see `06`).

### Log
- **Start/continue a session** (title + optional type + date). An active session is the default
  view of `/log`.
- **Add exercise** via `ExercisePicker` (searches the catalog; recent/favorites first).
- **`SetEntryPad`** — the core interaction. Fast numeric entry for weight/reps (or hold), RPE
  optional. Big touch targets (this is used mid-workout, one-handed, sweaty). Previous set
  pre-fills the next. Optimistic UI on save.
- **PR feedback:** when the API flags `is_pr`, celebrate it (motion + accent) — a signature
  moment (see `08`).
- **Rest timer** (nice-to-have): starts on set save.
- **Offline-first (PWA):** logging must survive a flaky gym connection. Queue set writes locally
  (IndexedDB) and sync when back online; the UI reflects pending/synced state. See PWA below.

### Home & progress
`/dashboard` is the **front door** (Phase 11C): the workout in progress, the last seven days as
four stats and a day strip, and one row each for the latest PR and top skill. Everything below is
a link to its own screen — except above 768px, where they render inline in home's right column.
- **Volume** (`/progress/volume`): sets/reps/tonnage over a selectable range (`analytics.volume`).
  The range control lives here, with the only data it governs.
- **Frequency** (`/progress/frequency`): sessions per ISO week (`analytics.frequency`) as a heatmap.
- **Records** (`/progress/records`): per-exercise best lifts/holds with the exercise illustration.
  All-time — `listPrs()` takes no window, so there is deliberately no range control.
- **Skills (secondary)** (`/progress/skills`): ring/stage visualization per calisthenics skill;
  edit current stage/%. Clearly a secondary module, not the front page.

## Data fetching & mutations

- **Reads:** Server Components call the API server-side (`lib/api.ts` forwards the session
  cookie) so the initial render is authenticated and fast. Use React `cache()`/`fetch` caching
  thoughtfully; user data is per-request (no shared cache).
- **API base:** browser calls go to `NEXT_PUBLIC_API_URL` (`https://api.tempo.clupai.com`) with
  `credentials: 'include'` and the `X-Tempo-Client` header (CORS + CSRF, see `05`/`09`).
  Server-side fetches forward the incoming session cookie to the same host.
- **Mutations:** Server Actions **or** client calls to the API with optimistic updates. Prefer
  optimistic UI for logging (it must feel instant). Revalidate affected server data on success.
- **Types:** generate a typed client from the FastAPI OpenAPI schema (e.g. `openapi-typescript`)
  so the frontend and backend contracts can't silently drift. Regenerate in CI.
- **Auth boundary:** the `(app)` layout checks the session server-side and redirects to
  `https://api.tempo.clupai.com/oauth/login/google` when absent. Never render app chrome for
  signed-out users.

## Settings → "Connected apps"

- Show the MCP connection status and a copy-able connector URL
  (`https://api.tempo.clupai.com/mcp`) with a short "Add Tempo to Claude" guide.
- List active OAuth clients (from `oauth_clients`/tokens) with a **revoke** action (revokes
  tokens for that client). This is the user-facing control for the OAuth grants from `05`.

## PWA / offline

- `manifest.webmanifest` + installable; app icon = the Tempo mark.
- Service worker: app-shell caching + an **offline write queue** for set logging (IndexedDB).
  On reconnect, flush the queue to `/api/sessions/{id}/sets`, resolving PR flags from the
  server response.
- Scope offline strictly to logging in v1 (the highest-value offline case); browsing/dashboard
  can require connectivity. Don't over-build offline.

## Accessibility & performance (non-negotiable for "flagship polish")

- Keyboard navigable everywhere; visible focus states; correct roles/labels.
- `prefers-reduced-motion` respected by all motion (see `08`).
- Core Web Vitals budget: LCP < 2.5s, CLS < 0.1, INP < 200ms. Illustrations via `<Image>`
  with explicit dimensions (no layout shift). Route-level code splitting.
- Color contrast meets WCAG AA against the dark x.ai palette.

## Definition of Done (per frontend slice)
- The slice's surface renders real data from the API for an authenticated user.
- Interactions are optimistic where specified; error/empty/loading/placeholder states exist.
- Motion follows `08` and passes the **Antigravity frontend review** gate.
- a11y + Core Web Vitals budgets met (checked in CI/Lighthouse).
- Typed API client regenerated; no `any` at the API boundary.
