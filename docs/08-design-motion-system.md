# 08 — Design & Motion System

Design bar: **flagship polish.** Motion is a first-class engineering concern, not decoration.
This doc turns "impeccable / taste / Emil Kowalski" into rules an executing agent — and the
**Antigravity frontend-review gate** — can apply objectively.

## Design system source

- Install the **x.ai design system** via the provided CLI:
  ```
  npx getdesign@latest add x.ai
  ```
  Run this in `apps/web` (or the shared `packages/ui`) during Phase 6. Integrate its components
  as the base layer; wrap them in `components/ui/` so app code depends on our wrappers, not the
  vendor API directly (swap-ability + consistency).
- Apply the design **skills** the user specified — `impeccable`, `taste`(design), and
  `emil-kowalski`(motion) — as the review rubric. Treat their guidance as authoritative for
  aesthetics/motion; the principles below are the codified, checkable version.

> The exact component API of `getdesign x.ai` is resolved at execution time from what the CLI
> installs. Do not hardcode assumptions here that contradict the installed system — reconcile,
> and record any deviation in the Decision Log.

## Aesthetic direction (x.ai vibe)

- **Dark, high-contrast, technical, minimal.** Near-black canvas, crisp near-white text, a
  single restrained accent. Lots of negative space. Nothing decorative that isn't functional.
- **Theme-aware:** support light + dark (dark is the signature); tokens drive both.
- **Typography:** one precise sans (the x.ai system's default if it ships one); a tight type
  scale; generous line-height for instructions; tabular figures for weights/reps/timers.
- **Surfaces:** subtle borders over heavy shadows; low-chroma; the exercise **line-art
  illustrations** are the primary visual texture — the chrome stays quiet so they sing.

## Design tokens (single source of truth)

Define tokens once (`design/tokens.css` as CSS custom properties, mirrored in TS for JS access).
Everything else references tokens — **no hardcoded hex, px, or ms in components.**

- **Color:** `--bg`, `--surface`, `--border`, `--text`, `--text-muted`, `--accent`,
  `--accent-muted`, `--success` (PR moment), `--danger`. Light/dark variants.
- **Space:** a 4px-based scale (`--space-1..12`).
- **Radius:** `--radius-sm/md/lg/full`.
- **Type:** `--font-sans`, `--text-xs..3xl`, weights, `--leading-*`.
- **Motion:** durations + easings as tokens (below) so motion is consistent and tunable.

## Motion rulebook (Emil-Kowalski-grade)

Motion should feel **fast, natural, purposeful, and interruptible** — you notice the app feels
alive, not that "things are animating."

### Principles (each is a review checkpoint)
1. **Purpose only.** Every animation communicates something — origin, hierarchy, state change,
   or feedback. If it doesn't, remove it.
2. **Fast.** Most transitions **150–250ms**; micro-feedback **~100ms**; only large spatial
   changes approach 300–400ms. Never slow enough to wait on.
3. **Natural easing.** Enters/moves use **ease-out** (decelerate); exits use ease-in. Use
   spring physics for anything the user "grabs"/drags. No linear easing except opacity fades.
4. **Animate cheap properties.** `transform` and `opacity` only (GPU-friendly). Never animate
   layout-triggering properties (width/height/top/left) — use transforms/`scale`, or FLIP.
5. **Origin-aware.** Things emerge from where they came from (a detail expands from its card;
   a menu scales from its trigger). Motion has spatial logic.
6. **Interruptible & reversible.** A user reversing an action mid-animation is handled
   gracefully; no janky queueing. State, not time, is the source of truth.
7. **Respect `prefers-reduced-motion`.** Provide a reduced variant: cross-fades/instant state
   instead of movement. This is mandatory, not optional.
8. **Choreography, not chaos.** Stagger related elements subtly (20–40ms) to guide the eye;
   avoid everything moving at once.

### Motion tokens
```
--ease-out: cubic-bezier(0.16, 1, 0.3, 1);      /* signature decelerate */
--ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
--dur-fast: 120ms;   --dur-base: 200ms;   --dur-slow: 320ms;
--spring: (tune via the motion lib: stiffness ~300, damping ~30)
```

### Implementation
- Use **CSS View Transitions** for route/page and list→detail transitions where supported;
  the App Router integrates with them. Provide graceful fallback.
- Use a spring/motion library (e.g. Framer Motion / Motion) for interactive, interruptible,
  gesture-driven pieces. Keep a small set of shared primitives in `components/motion/`
  (`FadeIn`, `Stagger`, `Sheet`, `Pressable`, `SharedElement`).
- No bespoke keyframes scattered in components — compose the primitives + tokens.

### Signature moments (worth extra craft)
- **PR celebration** on set save: accent bloom + a crisp, brief spring on the set row + the
  number counting to the new PR. This is the emotional peak of the app — make it excellent,
  but keep it <500ms and skippable under reduced-motion.
- **List → detail** in the Library: the exercise illustration performs a shared-element
  transition into the detail page.
- **Set entry:** each saved set settles into the list with a subtle origin-aware slide+fade.

## Component inventory (v1)

Build/warp these on top of the x.ai system:
`Button`, `IconButton`, `Input`, `NumberPad`, `Select`, `Tabs`, `Card`, `Sheet/Drawer`,
`Dialog`, `Toast`, `Badge/Tag` (muscle/equipment), `Avatar`, `Skeleton`,
`IllustrationImage` (with placeholder/loading states), `ExerciseCard`, `SetRow`,
`SkillRing`, `VolumeChart`, `FrequencyHeatmap`, `EmptyState`.

Each component ships with: all states (default/hover/focus/active/disabled/loading/empty),
keyboard support, reduced-motion variant, and token-only styling.

## The Antigravity review rubric (what the frontend gate checks)

A UI phase passes only if:
- [ ] Uses tokens exclusively — no hardcoded color/space/duration.
- [ ] Motion obeys the 8 principles; durations within the token ranges; reduced-motion variant present.
- [ ] Signature moments implemented where specified and feel crisp (not sluggish, not gratuitous).
- [ ] All component states exist; empty/error/loading/placeholder covered.
- [ ] a11y: keyboard nav, focus-visible, roles/labels, AA contrast on the dark palette.
- [ ] Performance: no layout-thrashing animations; CWV budgets met; images sized (no CLS).
- [ ] Matches the x.ai aesthetic (restraint, contrast, space) and the `impeccable`/`taste`
      skill guidance.

## Definition of Done (design-system phase)
- `getdesign x.ai` installed and integrated; token layer defined; `components/ui/` wrappers exist.
- `components/motion/` primitives exist with reduced-motion support and are used by at least
  one real surface.
- The rubric above is codified in the repo (e.g. a checklist doc/CI comment) so every later UI
  slice is measured against it.
