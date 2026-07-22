import { cn } from "@/lib/cn";
import styles from "./SkillRing.module.css";

export interface SkillRingProps {
  /** 0–100 through the current stage. */
  percent: number;
  currentStage: number;
  totalStages: number;
  /** Diameter in px. */
  size?: number;
}

const RADIUS = 42;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * A calisthenics-skill progress ring (docs/07 §Skills). The arc encodes percent-through-stage;
 * the center reads the current stage over its total. Presentational + token-styled; no motion on
 * the arc (a static viz — the card's enter animation carries the choreography). Works SSR or client.
 */
export function SkillRing({ percent, currentStage, totalStages, size = 96 }: SkillRingProps) {
  const clamped = Math.max(0, Math.min(100, percent));
  const offset = CIRCUMFERENCE * (1 - clamped / 100);
  const started = currentStage > 0 || clamped > 0;
  return (
    <svg
      className={styles.ring}
      width={size}
      height={size}
      viewBox="0 0 100 100"
      role="img"
      aria-label={`Stage ${currentStage} of ${totalStages}, ${clamped}% through`}
    >
      <circle className={styles.track} cx="50" cy="50" r={RADIUS} />
      {started && (
        <circle
          className={styles.progress}
          cx="50"
          cy="50"
          r={RADIUS}
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
        />
      )}
      <text x="50" y="47" className={cn(styles.stage, !started && styles.stageMuted)}>
        {currentStage}
      </text>
      <text x="50" y="64" className={styles.total}>
        of {totalStages}
      </text>
    </svg>
  );
}
