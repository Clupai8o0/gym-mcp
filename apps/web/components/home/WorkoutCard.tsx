import Link from "next/link";

// Deep import, not the barrel: it also exports `SessionLogger`, which pulls the `motion`
// runtime onto home — a screen with nothing to animate. Guarded by ESLint.
import { SessionStarter } from "@/components/log/SessionStarter";
import { Card, LocalTime } from "@/components/ui";
import type { Session } from "@/lib/types";
import styles from "./WorkoutCard.module.css";

export interface WorkoutCardProps {
  /** The in-progress session (Phase 11A's lifecycle flag), or `null` when not training. */
  active: Session | null;
  setCount: number;
}

/**
 * The one thing home exists to answer: are you mid-workout, and if not, can you start one now?
 * It sits directly under the date row so the workout is never below the fold — every other block
 * on this screen is a summary, and summaries can wait.
 */
export function WorkoutCard({ active, setCount }: WorkoutCardProps) {
  if (!active) {
    return (
      <Card padded className={styles.idle}>
        <div className={styles.idleText}>
          <p className="eyebrow">Ready when you are</p>
          <p className={styles.idleTitle}>No workout in progress</p>
        </div>
        <SessionStarter compact label="Start workout" variant="primary" />
      </Card>
    );
  }

  return (
    <Link href={`/log/${active.id}`} className={styles.link}>
      <Card interactive padded className={styles.active}>
        <div className={styles.activeText}>
          <p className={`eyebrow ${styles.live}`}>
            <span className={styles.pulse} aria-hidden />
            In progress
          </p>
          <p className={styles.activeTitle}>{active.title ?? "Workout"}</p>
          <p className={styles.activeMeta}>
            {setCount} set{setCount === 1 ? "" : "s"} · started{" "}
            <LocalTime iso={active.performed_at} format="time" />
          </p>
        </div>
        <span className={styles.cta} aria-hidden>
          Continue →
        </span>
      </Card>
    </Link>
  );
}
