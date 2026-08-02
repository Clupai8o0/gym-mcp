import { FadeIn } from "@/components/motion/FadeIn";
import type { ThemePreference } from "@/lib/theme";
import type { Exercise } from "@/lib/types";
import { ExerciseCard } from "./ExerciseCard";
import styles from "./ExerciseGrid.module.css";

/** Per-item delay step and cap — the same subtle 28ms/12-item choreography as `Stagger` (docs/08 §8). */
const STEP_MS = 28;
const MAX_STEPPED = 12;

export interface ExerciseGridProps {
  exercises: Exercise[];
  preference: ThemePreference;
  /**
   * How many tiles the server sent per request. The stagger delay is computed *within* a page, so
   * each batch appended on scroll cascades like the first one instead of every tile past the
   * twelfth sharing one flat delay.
   */
  pageSize?: number;
  /** Eager-load this many leading tiles — the LCP candidates (docs/07 CWV). */
  priorityCount?: number;
}

/**
 * The catalog grid. One grid container for every loaded page: appended tiles have to flow into the
 * same `auto-fill` track list as the first, or a page boundary that doesn't land on a row boundary
 * leaves a visible seam.
 *
 * Tiles are keyed by exercise id and `FadeIn` is a CSS animation on mount, so appending a page
 * animates only the new tiles — React keeps the existing DOM nodes untouched.
 */
export function ExerciseGrid({
  exercises,
  preference,
  pageSize,
  priorityCount = 6,
}: ExerciseGridProps) {
  const batch = pageSize && pageSize > 0 ? pageSize : exercises.length || 1;
  return (
    <div className={styles.grid}>
      {exercises.map((exercise, index) => (
        <FadeIn key={exercise.id} delay={Math.min(index % batch, MAX_STEPPED) * STEP_MS}>
          <ExerciseCard
            exercise={exercise}
            preference={preference}
            priority={index < priorityCount}
          />
        </FadeIn>
      ))}
    </div>
  );
}
