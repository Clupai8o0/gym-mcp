"use client";

import { motion, useReducedMotion } from "motion/react";

import { spring } from "@/design/motion";
import { formatWeight } from "@/lib/format";
import type { UnitPref } from "@/lib/types";
import { CountUp } from "./CountUp";
import styles from "./PrCelebration.module.css";

export interface PrCelebrationProps {
  prType: string;
  value: number | null;
  unitPref: UnitPref;
  /** When true, play the one-time bloom + count-up; otherwise render the record statically. */
  celebrate: boolean;
}

function SparkIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"
        fill="currentColor"
      />
    </svg>
  );
}

/** Map a PR verdict to a label + a value formatter (the count-up target). */
function describe(prType: string, unitPref: UnitPref): { label: string; format: (n: number) => string } | null {
  switch (prType) {
    case "weight":
      return { label: "Heaviest", format: (n) => formatWeight(n, unitPref) };
    case "reps":
      return { label: "Most reps", format: (n) => `${Math.round(n)} reps` };
    case "hold_time":
      return { label: "Longest hold", format: (n) => `${Math.round(n)}s` };
    case "first_log":
      return { label: "First logged", format: () => "New" };
    default:
      return null;
  }
}

/**
 * The PR celebration (docs/08 signature moment) — an accent bloom + count-up on the set that set a
 * record. Kept <500ms and skippable: under reduced motion the chip simply appears with its final
 * value. Rendered inline on the PR set row; `celebrate` gates the one-time bloom.
 */
export function PrCelebration({ prType, value, unitPref, celebrate }: PrCelebrationProps) {
  const reduce = useReducedMotion();
  const meta = describe(prType, unitPref);
  if (!meta) return null;

  const showCount = value != null && prType !== "first_log";
  const initial = celebrate && !reduce ? { scale: 0.6, opacity: 0 } : false;

  return (
    <motion.span
      className={styles.chip}
      role="status"
      initial={initial}
      animate={{ scale: 1, opacity: 1 }}
      transition={spring}
    >
      {celebrate && !reduce && <span className={styles.bloom} aria-hidden />}
      <SparkIcon />
      <span className={styles.label}>New PR</span>
      {showCount ? (
        <span className={`${styles.value} tnum`}>
          {celebrate ? (
            <CountUp value={value as number} format={meta.format} />
          ) : (
            meta.format(value as number)
          )}
        </span>
      ) : (
        <span className={styles.value}>{meta.label}</span>
      )}
    </motion.span>
  );
}
