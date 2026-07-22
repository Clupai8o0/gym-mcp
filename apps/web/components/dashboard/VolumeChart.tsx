import { Card } from "@/components/ui";
import { formatCount, formatTonnage } from "@/lib/format";
import type { UnitPref, Volume } from "@/lib/types";
import styles from "./VolumeChart.module.css";

const TOP_N = 8;

/**
 * Training volume for the selected range: three headline totals + a ranked bar list of the
 * busiest movements (docs/07 §Dashboard). Bar length encodes total sets — the one metric always
 * present (tonnage is null for bodyweight work) — with tonnage annotated where it exists. Pure
 * server component; bars are token-styled divs (no chart lib, no CLS).
 */
export function VolumeChart({ volume, unit }: { volume: Volume; unit: UnitPref }) {
  const items = volume.items;
  const totalSets = items.reduce((sum, item) => sum + item.total_sets, 0);
  const totalReps = items.reduce((sum, item) => sum + item.total_reps, 0);
  const totalTonnage = items.reduce((sum, item) => sum + (item.total_tonnage_kg ?? 0), 0);

  const top = [...items].sort((a, b) => b.total_sets - a.total_sets).slice(0, TOP_N);
  const maxSets = Math.max(...top.map((item) => item.total_sets), 1);

  return (
    <Card className={styles.card}>
      <dl className={styles.totals}>
        <div className={styles.total}>
          <dt className={styles.totalLabel}>Sets</dt>
          <dd className={`${styles.totalValue} tnum`}>{formatCount(totalSets)}</dd>
        </div>
        <div className={styles.total}>
          <dt className={styles.totalLabel}>Reps</dt>
          <dd className={`${styles.totalValue} tnum`}>{formatCount(totalReps)}</dd>
        </div>
        <div className={styles.total}>
          <dt className={styles.totalLabel}>Tonnage</dt>
          <dd className={`${styles.totalValue} tnum`}>
            {totalTonnage > 0 ? formatTonnage(totalTonnage, unit) : "—"}
          </dd>
        </div>
      </dl>

      <ul className={styles.bars}>
        {top.map((item) => {
          const width = `${Math.max(4, Math.round((item.total_sets / maxSets) * 100))}%`;
          return (
            <li key={item.exercise_id} className={styles.row}>
              <span className={styles.rowName} title={item.exercise_name}>
                {item.exercise_name}
              </span>
              <span className={styles.track} aria-hidden>
                <span className={styles.fill} style={{ width }} />
              </span>
              <span className={`${styles.rowValue} tnum`}>
                {item.total_sets}
                <span className={styles.rowUnit}> sets</span>
                {item.total_tonnage_kg != null && (
                  <span className={styles.rowTonnage}>
                    {" · "}
                    {formatTonnage(item.total_tonnage_kg, unit)}
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
