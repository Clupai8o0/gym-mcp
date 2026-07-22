# Frontend review rubric (the Antigravity gate)

Codified from [`docs/08-design-motion-system.md`](../../docs/08-design-motion-system.md). **Every
UI phase (6–9) is measured against this before its PR merges.** The Antigravity CLI runs it on UI
phases; this file is the source list so the check is objective and repeatable. The base design
spec is [`DESIGN.md`](./DESIGN.md) (the getdesign `x.ai` system); the token layer is
[`design/tokens.css`](./design/tokens.css).

## Checklist

### 1. Tokens only — no hardcoded values

- [ ] No literal hex, rgb, px, rem-magic, or ms in components — everything references a
      `var(--token)` from `design/tokens.css`. (Exception: structural values like `0`, `1px`
      borders, `100%`, `1fr`, `50%`.)
- [ ] Color, space, radius, type, and motion all come from the token scale.
- [ ] New values are added to the token layer first, then referenced — not inlined.

### 2. Motion obeys the 8 principles (docs/08)

- [ ] **Purpose** — every animation communicates origin/hierarchy/state/feedback.
- [ ] **Fast** — 150–250ms typical, ~100ms micro, ≤~320ms only for large spatial moves.
- [ ] **Natural easing** — enters `--ease-out`, exits ease-in; no linear except opacity.
- [ ] **Cheap properties** — `transform`/`opacity` only; never animate width/height/top/left.
- [ ] **Origin-aware** — things emerge from where they came from.
- [ ] **Interruptible** — reversing mid-animation is graceful (spring/state-driven).
- [ ] **Reduced motion** — every motion has a reduced variant (verified with the OS setting on).
- [ ] **Choreography** — related elements stagger subtly (20–40ms), not all-at-once.
- [ ] Motion is composed from `components/motion/` primitives + tokens — no scattered keyframes.

### 3. Signature moments (where specified)

- [ ] Implemented and crisp — not sluggish, not gratuitous, skippable under reduced motion.
- Phase 6: **Library list → detail** shared-element illustration morph.
- Phase 7: **PR celebration** on set save (<500ms).

### 4. All component states

- [ ] default / hover / focus-visible / active / disabled / loading present where applicable.
- [ ] empty / error / loading / placeholder states exist for every data surface.

### 5. Accessibility (AA)

- [ ] Keyboard navigable end-to-end; visible `:focus-visible` ring.
- [ ] Correct roles/labels; icon-only controls have accessible names.
- [ ] Color contrast meets WCAG AA against the dark palette.
- [ ] `next/image` alt text is meaningful.

### 6. Performance / Core Web Vitals

- [ ] No layout-thrashing animations (transform/opacity only).
- [ ] Images sized (explicit dimensions or `fill` + aspect-ratio) — **no CLS**.
- [ ] Budgets: LCP < 2.5s, CLS < 0.1, INP < 200ms.
- [ ] Route-level code splitting; client components kept to interaction/motion.

### 7. x.ai aesthetic (restraint, contrast, space)

- [ ] Near-black canvas, crisp text, single restrained accent, generous negative space.
- [ ] Pills for interactive shapes; hairline borders over heavy shadows.
- [ ] Universal-Sans-substitute display + Geist-Mono uppercase eyebrows; tabular figures for numbers.
- [ ] Matches the `impeccable` / `taste` skill guidance.

## Contract hygiene (docs/07 DoD)

- [ ] Typed API client regenerated (`pnpm --filter @tempo/web gen:api`); **no `any` at the API
      boundary**. `lib/api-types.ts` derives from the FastAPI OpenAPI schema (`openapi.json`).
- [ ] `pnpm exec turbo run build lint typecheck` is green.
