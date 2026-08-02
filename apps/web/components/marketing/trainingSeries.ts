/**
 * The sample training block the marketing hero draws. Sample, not real: it is generated, and the
 * hero caption says so. Nothing here is ever presented as a user's actual training.
 *
 * Deterministic by construction. Integer hashing only, no `Math.random` and no non-integer
 * `Math.pow`, both of which can differ in their last bits between Node and a browser engine and
 * would surface as a hydration mismatch once the values are rounded.
 */
export const TRAINING_DAYS = 182;

/** 13 lines of 14 days. A fortnight per line reads as a rhythm; a week is too short to have one. */
export const RIDGE_ROWS = 13;
export const RIDGE_DAYS = TRAINING_DAYS / RIDGE_ROWS;

function hash(index: number): number {
  let x = (index * 1664525 + 1013904223) >>> 0;
  x ^= x >>> 15;
  x = Math.imul(x, 2246822519) >>> 0;
  x ^= x >>> 13;
  return (x >>> 0) / 4294967296;
}

/** Wednesday and Sunday read as rest across the whole block. */
function isRest(index: number): boolean {
  const day = index % 7;
  return day === 2 || day === 6;
}

/**
 * The block's shape: near-flat at the start, spiky by the end.
 *
 * Two things ramp together, and that pairing is what makes the growth legible rather than merely
 * present. The trend is quadratic, so the first months stay genuinely low instead of climbing
 * from a high floor. The spread widens alongside it, so early lines barely leave their baseline
 * while recent ones swing hard. A flat line turning jagged reads as "this got harder" much faster
 * than thirteen equally spiky lines sitting at rising heights.
 */
function intensityAt(index: number): number {
  if (isRest(index)) return 0.05;
  const p = index / (TRAINING_DAYS - 1);
  const trend = 0.08 + 0.78 * p * p;
  const spread = 0.15 + 0.85 * p;
  const value = Math.min(1, Math.max(0.05, trend * (1 - 0.5 * spread + spread * hash(index))));
  return Math.round(value * 1000) / 1000;
}

export interface TrainingDay {
  index: number;
  /** 0 to 1. Rest days sit just above zero so the line never has a true hole in it. */
  intensity: number;
}

export const trainingDays: TrainingDay[] = Array.from({ length: TRAINING_DAYS }, (_, index) => ({
  index,
  intensity: intensityAt(index),
}));

/** Round to 2dp so emitted path strings stay short and byte-identical across renders. */
function r2(value: number): number {
  return Math.round(value * 100) / 100;
}

/**
 * Smooth a point list into an SVG path. Quadratic segments anchored on each point with midpoints
 * as endpoints: cheap, stable, and it never overshoots the way a naive Catmull-Rom spline does on
 * the sharp rest-day notches.
 *
 * Every emitted number is rounded here rather than by the caller, because the midpoints are
 * computed from already-rounded inputs and would otherwise reintroduce values like
 * 15.469999999999999 into the markup.
 */
function smoothPath(points: Array<{ x: number; y: number }>): string {
  if (points.length === 0) return "";
  const first = points[0]!;
  if (points.length === 1) return `M ${r2(first.x)} ${r2(first.y)}`;

  let d = `M ${r2(first.x)} ${r2(first.y)}`;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1]!;
    const point = points[i]!;
    d += ` Q ${r2(prev.x)} ${r2(prev.y)} ${r2((prev.x + point.x) / 2)} ${r2((prev.y + point.y) / 2)}`;
  }
  const last = points[points.length - 1]!;
  return `${d} L ${r2(last.x)} ${r2(last.y)}`;
}

export interface RidgeLine {
  row: number;
  d: string;
  /** Percentage for the accent side of the `color-mix`, oldest 0% to newest 100%. */
  mix: string;
  opacity: number;
}

const AMPLITUDE = 13;
const BASELINE_START = 10;
const BASELINE_STEP = 6.5;
const MIN_OPACITY = 0.35;

/**
 * Precomputed at module load. These never change, so there is no reason to rebuild them on each
 * render of a page that is otherwise fully static.
 */
export const ridgeLines: RidgeLine[] = Array.from({ length: RIDGE_ROWS }, (_, row) => {
  const days = trainingDays.slice(row * RIDGE_DAYS, (row + 1) * RIDGE_DAYS);
  const baseline = BASELINE_START + row * BASELINE_STEP;
  const t = row / (RIDGE_ROWS - 1);
  return {
    row,
    d: smoothPath(
      days.map((day, i) => ({
        x: (i / (RIDGE_DAYS - 1)) * 100,
        y: baseline - day.intensity * AMPLITUDE,
      })),
    ),
    mix: `${Math.round(t * 100)}%`,
    opacity: r2(MIN_OPACITY + (1 - MIN_OPACITY) * t),
  };
});
