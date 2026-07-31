import Link from "next/link";

import { formatCount, formatTonnage } from "@/lib/format";
import type { UnitPref } from "@/lib/types";
import styles from "./WeekStats.module.css";

export interface WeekStatsProps {
  sessions: number;
  tonnageKg: number;
  sets: number;
  prs: number;
  unit: UnitPref;
}

/**
 * Four numbers for the last seven days: Sessions · Tonnage · Sets · PRs.
 *
 * The window is a **rolling** seven days rather than a calendar week on purpose — a rolling
 * window is defined by two instants, so it means the same thing in every timezone, whereas
 * "since Monday" would have to be resolved somewhere and the server only knows UTC (the same
 * trap the old `isToday` heuristic fell into — see Decision Log D31/D33).
 */
export function WeekStats({ sessions, tonnageKg, sets, prs, unit }: WeekStatsProps) {
  // The unit is split out so a four-up row on a 393px screen never wraps "1,488 kg" onto two
  // lines and makes one tile taller than its neighbours.
  const stats = [
    { label: "Sessions", value: formatCount(sessions), href: "/progress/frequency" },
    {
      label: "Tonnage",
      value: tonnageKg > 0 ? formatTonnage(tonnageKg, unit, { withUnit: false }) : "—",
      unit: tonnageKg > 0 ? unit : undefined,
      href: "/progress/volume",
    },
    { label: "Sets", value: formatCount(sets), href: "/progress/volume" },
    { label: "PRs", value: formatCount(prs), href: "/progress/records" },
  ];

  return (
    <section aria-label="Last 7 days">
      <p className={`eyebrow ${styles.caption}`}>Last 7 days</p>
      <ul className={styles.grid}>
        {stats.map((stat) => (
          <li key={stat.label}>
            <Link href={stat.href} className={styles.tile}>
              <span className={styles.valueRow}>
                <span className={`${styles.value} tnum`}>{stat.value}</span>
                {stat.unit && <span className={styles.unit}>{stat.unit}</span>}
              </span>
              <span className={styles.label}>{stat.label}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
