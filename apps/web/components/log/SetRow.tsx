"use client";

import { motion, useReducedMotion } from "motion/react";

import { Spinner } from "@/components/ui";
import { durations, easings, enterTransition } from "@/design/motion";
import { formatSetSummary } from "@/lib/format";
import type { UnitPref } from "@/lib/types";
import { PrCelebration } from "./PrCelebration";
import type { LogSet } from "./types";
import styles from "./SetRow.module.css";

export interface SetRowProps {
  set: LogSet;
  unitPref: UnitPref;
  /** Play the one-time PR bloom for a set that just set a record. */
  celebrate: boolean;
  onDelete: () => void;
  onRetry: () => void;
}

function OfflineGlyph() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 4l16 16M8.5 8.6A7 7 0 003 12m6.9-4.7A9 9 0 0121 12M6.5 12a4.5 4.5 0 013-1.3M12 20h.01"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * One logged set. Enters with a subtle origin-aware slide+fade as it settles into the list
 * (docs/08 signature). Shows saving/queued/error status, the metric summary, and — when the set
 * set a record — the PR celebration. `transform`/`opacity` only; reduced motion → instant.
 */
export function SetRow({ set, unitPref, celebrate, onDelete, onRetry }: SetRowProps) {
  const reduce = useReducedMotion();
  return (
    <motion.li
      className={styles.row}
      data-status={set.status}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={
        reduce
          ? { opacity: 0 }
          : { opacity: 0, y: -8, transition: { duration: durations.fast, ease: easings.in } }
      }
      transition={enterTransition}
    >
      <span className={styles.number} aria-hidden>
        {set.setNumber}
      </span>

      <span className={`${styles.summary} tnum`}>
        {formatSetSummary(
          { weight_kg: set.weightKg, reps: set.reps, hold_seconds: set.holdSeconds },
          unitPref,
        )}
        {set.rpe != null && <span className={styles.rpe}>RPE {set.rpe}</span>}
      </span>

      <span className={styles.status}>
        {set.isPr && (
          <PrCelebration
            prType={set.prType ?? "first_log"}
            value={set.prValue}
            unitPref={unitPref}
            celebrate={celebrate}
          />
        )}
        {set.status === "saving" && <Spinner className={styles.spinner} />}
        {set.status === "queued" && (
          <span className={styles.queued}>
            <OfflineGlyph />
            Queued
          </span>
        )}
        {set.status === "error" && (
          <button type="button" className={styles.retry} onClick={onRetry}>
            Retry
          </button>
        )}
      </span>

      <button
        type="button"
        className={styles.delete}
        onClick={onDelete}
        aria-label={`Delete set ${set.setNumber}`}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
          <path
            d="M6 7h12M9 7V5h6v2M8 7l1 12h6l1-12"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
    </motion.li>
  );
}
