/**
 * Motion tokens for the `motion/react` library, mirroring the `--dur-*` CSS tokens so JS- and
 * CSS-driven motion stay in lockstep (docs/08). Durations are in **seconds** (the unit
 * `motion` expects); the CSS tokens carry the same values in `ms`.
 *
 * Rulebook (docs/08 §Motion): most transitions 150–250ms, micro-feedback ~100ms, only large
 * spatial changes approach ~320ms. Never linear except opacity.
 */
import { easings } from "./easings";

/** Durations in seconds (motion's unit). */
export const durations = {
  micro: 0.1,
  fast: 0.12,
  base: 0.2,
  slow: 0.32,
} as const;

/** The PR count-up run time in **ms** — mirrors the `--dur-count` CSS token; kept <500ms budget. */
export const countUpMs = 300;

/** Press-feedback scales — mirror the `--press-scale*` CSS tokens (docs/08 §3). */
export const pressScale = 0.97;
export const pressScaleStrong = 0.94;

/** The one spring for anything the user "grabs" or that should feel physical (docs/08 §3). */
export const spring = {
  type: "spring",
  stiffness: 300,
  damping: 30,
  mass: 1,
} as const;

/** Standard enter transition: fast, decelerating. */
export const enterTransition = {
  duration: durations.base,
  ease: easings.out,
} as const;

export { easings };
