"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { durations, easings } from "@/design/motion";
import { formatClock } from "@/lib/format";
import styles from "./RestTimer.module.css";

export interface RestTimerProps {
  /** Whether the timer bar is shown. */
  active: boolean;
  /** Bumped each time a set is logged — restarts the countdown from `seconds`. */
  startKey: number;
  onDismiss: () => void;
  seconds?: number;
}

/**
 * A compact rest countdown that starts on set save (docs/07 §Rest timer, nice-to-have). Restarts
 * whenever `startKey` changes; ticks once a second; +30s / skip controls. Slides up from the
 * bottom via `motion`; reduced motion cross-fades. Purely time display — no layout thrash.
 */
export function RestTimer({ active, startKey, onDismiss, seconds = 90 }: RestTimerProps) {
  const reduce = useReducedMotion();
  const [remaining, setRemaining] = useState(seconds);
  const endRef = useRef(0);

  // Restart on each new set (startKey) and tick down. All time reads happen inside the effect /
  // its interval callback (never during render), so the countdown stays pure per the lint rules.
  useEffect(() => {
    if (!active) return;
    endRef.current = Date.now() + seconds * 1000;
    const update = () => setRemaining(Math.max(0, Math.round((endRef.current - Date.now()) / 1000)));
    update();
    const id = setInterval(update, 500);
    return () => clearInterval(id);
  }, [active, startKey, seconds]);

  // +30s extends the current countdown without restarting it.
  const addThirty = () => {
    endRef.current += 30_000;
    setRemaining((r) => r + 30);
  };

  const done = remaining === 0;
  const progress = Math.min(1, Math.max(0, remaining / seconds));

  const slide = reduce ? { opacity: 0 } : { opacity: 0, y: 24 };

  return (
    <AnimatePresence>
      {active && (
        <motion.div
          className={styles.bar}
          data-done={done || undefined}
          role="timer"
          aria-label={done ? "Rest complete" : `Rest ${formatClock(remaining)} remaining`}
          initial={slide}
          animate={{ opacity: 1, y: 0 }}
          exit={slide}
          transition={{ duration: durations.base, ease: easings.out }}
        >
          <span className={styles.track} aria-hidden>
            <span className={styles.fill} style={{ transform: `scaleX(${progress})` }} />
          </span>
          <span className={styles.readout}>
            <span className={styles.label}>{done ? "Rest done" : "Rest"}</span>
            <span className={`${styles.time} tnum`}>{formatClock(remaining)}</span>
          </span>
          <span className={styles.controls}>
            <button type="button" className={styles.control} onClick={addThirty}>
              +30s
            </button>
            <button type="button" className={styles.control} onClick={onDismiss}>
              Skip
            </button>
          </span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
