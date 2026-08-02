# HANDOVER — theme toggle + theme-aware illustrations

**For a parallel Claude Code session. Scope is `apps/web` only.**

Another session is running the Phase 4 illustration batch against Neon and Vercel Blob right now.
Read [Ground rules](#ground-rules) before touching anything — some of this repo is actively
being written to.

---

## What already exists (do not rebuild)

`apps/web/design/tokens.css` **already ships a complete light theme.** A full token set — bg,
surface, border, text, accent, success/danger, outline, focus ring, input border, overlay,
shadow — is defined for light under `@media (prefers-color-scheme: light)`, with contrast values
already reconciled against the WCAG AA gate in `docs/08` (e.g. the light accent is `#d95c0a`,
darkened from the dark theme's `#ff7a17` so it clears 4.5:1 on white).

`apps/web/app/layout.tsx` already declares `colorScheme: "dark light"` and per-theme
`themeColor` entries.

**So the app already follows the OS setting today.** Dark is the signature and the default.
Your job is not to author a light theme. It is to make the theme *selectable*, and to make the
illustrations follow it.

---

## The work — three parts

### 1. Make `[data-theme]` actually work

The override hooks are half-built. Today:

```css
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) { /* ...all light tokens... */ }
}
:root[data-theme="dark"] { color-scheme: dark; }   /* only sets color-scheme */
```

Every light token lives *inside* the `prefers-color-scheme: light` media query. So
`data-theme="light"` on a machine whose OS is dark applies **nothing** — there is no rule
outside that query that can deliver light tokens. Forcing light is currently impossible.

Restructure so the light token block is authored once and applied by either trigger — the
system preference *or* an explicit `[data-theme="light"]`. A custom-property indirection or a
shared selector list both work; pick whichever keeps the file readable. Requirements:

- `data-theme="light"` forces light regardless of OS.
- `data-theme="dark"` forces dark regardless of OS.
- No `data-theme` attribute → follow the OS, exactly as today.
- `color-scheme` must be correct in all three cases (it drives native form controls and
  scrollbars).
- **Do not restate token values.** Duplicating the light palette into a second block is the
  failure mode here — it will drift.

### 2. Theme toggle UI

Three states: **light / dark / system**. Do not ship a two-state toggle; "system" must remain
reachable, and it is the default.

- Persist the choice (`localStorage`).
- Put it in settings. **Mirror `components/settings/UnitToggle.tsx`** — it is the established
  segmented-control pattern in this codebase, including its CSS-module conventions. Match it
  rather than inventing a new control.
- **Prevent the flash.** A persisted preference must be stamped onto `<html>` *before first
  paint*, via a small blocking inline script in the root layout. Without it the page paints dark,
  then snaps to light on hydration. This is the single most visible way to get this task wrong.
- The toggle must be keyboard operable and screen-reader labelled (`docs/08` a11y gate).

### 3. Theme-aware illustrations

This is why the task exists.

Each exercise now has **two** illustration assets. The API returns both:

| field | asset |
|---|---|
| `illustration_url` | bold off-white linework — for **dark** surfaces |
| `illustration_url_light` | same art, linework inverted to near-black — for **light** surfaces |

The amber working-muscle accent (`#F2A03D`) is byte-identical in both. `illustration_url_light`
is non-NULL exactly when `illustration_url` is.

**Why two assets and not a CSS filter:** `filter: invert()` cannot act selectively — it would
drag the amber accent to blue. The light twin is derived server-side by inverting only the
achromatic pixels. Do not try to replace it with a CSS filter; it will break the accent.

Wire it up in **`apps/web/components/library/IllustrationImage.tsx`**, which currently takes a
single `url` prop. Callers to update: `app/(app)/library/[slug]/page.tsx` and
`components/library/ExerciseCard.tsx`.

Constraints:

- Must react to the resolved theme *including* a mid-session toggle — not just initial load.
- Must not cause a layout shift or break the shared-element morph (`SharedElement`) that
  animates the illustration from the grid into the detail hero.
- Must not regress LCP on the detail page — the hero illustration is the LCP element and is
  currently `priority`.
- Prefer a solution that lets the browser pick without a JS round-trip if you can manage it
  while satisfying the above (`<picture>` + `prefers-color-scheme` is the obvious candidate, but
  note it will **not** respond to a manual `data-theme` override — that is the tension to solve).

**Regenerate the API types first.** `apps/web/openapi.json` and `apps/web/lib/api-types.ts` are
stale — neither has `illustration_url_light`. The live deployed schema does:

```bash
curl -s https://api.tempo.clupai.com/openapi.json -o apps/web/openapi.json
cd apps/web && pnpm gen:api
```

---

## Ground rules

**Work only inside `apps/web`.** A batch job is live against the production Neon database and
Vercel Blob store.

- **Do not** run `alembic`, any migration, or anything in `scripts/`.
- **Do not** modify `apps/api` — another session owns it. `openapi.json` is the contract; consume
  it, don't change it.
- **Do not** `git stash`, `git checkout .`, or revert anything. The working tree holds a large set
  of uncommitted Phase 4 changes plus a `.gitignore` fix that keeps real secrets out of git.
  Reverting it would expose credentials.
- **Do not** commit anything outside `apps/web` (plus the regenerated `openapi.json` /
  `lib/api-types.ts`).
- `.env.production` exists at the repo root and holds **live credentials**. Never read, print,
  echo, or commit it. You do not need it.

## Project conventions (enforced)

- **Tokens only.** No hardcoded hex, px, or ms in components — everything is `var(--token)` from
  `design/tokens.css`. This is a hard guardrail in `CLAUDE.md`.
- Motion follows the rulebook in `docs/08-design-motion-system.md`, including
  `prefers-reduced-motion`.
- TypeScript strict; no `any` at the API boundary — use the generated types.
- Conventional Commits.

## Definition of done

- [ ] `data-theme="light"` forces light on a dark-OS machine; `"dark"` forces dark on a light-OS
      machine; absent follows the OS.
- [ ] Light token values are authored **once**, not duplicated.
- [ ] Toggle offers light/dark/system, persists, is keyboard accessible and labelled.
- [ ] **No flash of the wrong theme on reload** with a non-system preference stored.
- [ ] Illustrations switch asset with the theme, including on a mid-session toggle.
- [ ] No CLS, no broken shared-element morph, LCP not regressed.
- [ ] `pnpm --filter @tempo/web lint typecheck build` clean.
- [ ] Verified at both themes in the running app, not just asserted.

## Reference

- `docs/08-design-motion-system.md` — design + motion rulebook, a11y gate
- `docs/07-frontend-nextjs.md` — frontend architecture
- `docs/06-catalog-and-images.md` — illustration pipeline and the locked style
- `apps/web/DESIGN.md` — the x.ai-derived system these tokens came from
