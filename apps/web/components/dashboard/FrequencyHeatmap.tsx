import { Card } from "@/components/ui";
import { cn } from "@/lib/cn";
import { formatCount, formatWeekLabel } from "@/lib/format";
import type { Frequency } from "@/lib/types";
import styles from "./FrequencyHeatmap.module.css";

/** Map a session count to one of five intensity buckets (0 = none … 4 = 4+ sessions). */
function level(count: number): number {
  if (count <= 0) return 0;
  return Math.min(count, 4);
}

/**
 * Sessions-per-ISO-week as a heatmap strip (docs/07 §Dashboard). Monday-anchored, zero-filled
 * weeks in from the API; each cell's intensity is a token-driven `color-mix` of the accent, so it
 * stays theme-aware and tokens-only. Server component — a11y via a summary label + per-cell title.
 */
export function FrequencyHeatmap({ frequency }: { frequency: Frequency }) {
  const items = frequency.items;
  const totalSessions = items.reduce((sum, item) => sum + item.count, 0);
  const activeWeeks = items.filter((item) => item.count > 0).length;
  const first = items[0];
  const last = items[items.length - 1];

  return (
    <Card className={styles.card}>
      <dl className={styles.totals}>
        <div className={styles.total}>
          <dt className={styles.totalLabel}>Sessions</dt>
          <dd className={`${styles.totalValue} tnum`}>{formatCount(totalSessions)}</dd>
        </div>
        <div className={styles.total}>
          <dt className={styles.totalLabel}>Active weeks</dt>
          <dd className={`${styles.totalValue} tnum`}>
            {activeWeeks}
            <span className={styles.totalMuted}>/{frequency.weeks}</span>
          </dd>
        </div>
      </dl>

      <div
        className={styles.strip}
        role="img"
        aria-label={`Training frequency: ${totalSessions} sessions across ${frequency.weeks} weeks`}
      >
        {items.map((item) => (
          <span
            key={item.week_start}
            className={cn(styles.cell, styles[`l${level(item.count)}`])}
            title={`Week of ${formatWeekLabel(item.week_start)} — ${item.count} ${
              item.count === 1 ? "session" : "sessions"
            }`}
          />
        ))}
      </div>

      <div className={styles.axis}>
        {first && <span>{formatWeekLabel(first.week_start)}</span>}
        <span className={styles.legend} aria-hidden>
          <span className={styles.legendLabel}>Less</span>
          <span className={cn(styles.cell, styles.l0)} />
          <span className={cn(styles.cell, styles.l1)} />
          <span className={cn(styles.cell, styles.l2)} />
          <span className={cn(styles.cell, styles.l3)} />
          <span className={cn(styles.cell, styles.l4)} />
          <span className={styles.legendLabel}>More</span>
        </span>
        {last && <span>{formatWeekLabel(last.week_start)}</span>}
      </div>
    </Card>
  );
}
