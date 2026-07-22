"use client";

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";

import { easings } from "@/design/motion";

export interface CountUpProps {
  value: number;
  /** Render the (possibly fractional) animated value. */
  format: (n: number) => string;
  /** Total run time; kept short so the PR moment stays <500ms (docs/08). */
  durationMs?: number;
  className?: string;
}

// The signature decelerate curve, sampled directly so the count matches the accent bloom's easing.
function easeOut(t: number): number {
  const [, y1, , y2] = easings.out;
  // Cubic-bezier with x1=0.16,x2=0.3 ≈ near-linear-in-t for our purposes; approximate on y.
  const u = 1 - t;
  return 3 * u * u * t * y1 + 3 * u * t * t * y2 + t * t * t;
}

/**
 * Counts a number up to `value` on mount — the numeric half of the PR celebration (docs/08
 * signature moment). `transform`/text only (no layout thrash); reduced motion shows the final
 * value immediately.
 */
export function CountUp({ value, format, durationMs = 420, className }: CountUpProps) {
  const reduce = useReducedMotion();
  const [display, setDisplay] = useState(reduce ? value : 0);
  const frame = useRef<number>(0);

  useEffect(() => {
    if (reduce) return; // final value is already the initial state — nothing to animate
    let start = 0;
    const tick = (now: number) => {
      if (!start) start = now;
      const t = Math.min(1, (now - start) / durationMs);
      setDisplay(value * easeOut(t));
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [value, durationMs, reduce]);

  return (
    <span className={className} aria-label={format(value)}>
      <span aria-hidden>{format(display)}</span>
    </span>
  );
}
