/**
 * Easing curves — the single source of truth, mirrored 1:1 by the `--ease-*` CSS tokens in
 * `tokens.css`. Exported as cubic-bezier control-point tuples so the motion library
 * (`motion/react`) and CSS animations share identical curves (docs/08 motion rulebook §3).
 *
 * Enters/moves decelerate (`out`); exits accelerate (`in`); spatial moves use `inOut`.
 */
export const easings = {
  /** Signature decelerate — enters and things arriving. `cubic-bezier(0.16, 1, 0.3, 1)`. */
  out: [0.16, 1, 0.3, 1],
  /** Symmetric — elements moving between two on-screen positions. */
  inOut: [0.65, 0, 0.35, 1],
  /** Accelerate — exits and things leaving. */
  in: [0.4, 0, 1, 1],
} as const;

export type EasingName = keyof typeof easings;
