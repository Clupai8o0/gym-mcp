import Link from "next/link";

import { Badge, LocalTime } from "@/components/ui";
import { IllustrationImage } from "@/components/library/IllustrationImage";
import { Stagger } from "@/components/motion/Stagger";
import { formatPrValue, prTypeLabel } from "@/lib/format";
import type { Pr, UnitPref } from "@/lib/types";
import styles from "./PrList.module.css";

/** One exercise and every personal record the user holds for it (weight/reps/hold). */
interface PrGroup {
  exerciseId: string;
  slug: string;
  name: string;
  illustrationUrl: string | null;
  illustrationStatus: string;
  isCustom: boolean;
  prs: Pr[];
  latest: string;
}

// Canonical order so a card always reads weight → reps → hold → first-log.
const PR_TYPE_ORDER: Record<string, number> = { weight: 0, reps: 1, hold_time: 2, first_log: 3 };

/** Collapse the flat PR list into one card per exercise, freshest achievement first. */
function groupByExercise(prs: Pr[]): PrGroup[] {
  const groups = new Map<string, PrGroup>();
  for (const pr of prs) {
    let group = groups.get(pr.exercise_id);
    if (!group) {
      group = {
        exerciseId: pr.exercise_id,
        slug: pr.exercise_slug,
        name: pr.exercise_name,
        illustrationUrl: pr.illustration_url,
        illustrationStatus: pr.illustration_status,
        isCustom: pr.is_custom,
        prs: [],
        latest: pr.achieved_at,
      };
      groups.set(pr.exercise_id, group);
    }
    group.prs.push(pr);
    if (pr.achieved_at > group.latest) group.latest = pr.achieved_at;
  }
  const result = [...groups.values()];
  for (const group of result) {
    group.prs.sort((a, b) => (PR_TYPE_ORDER[a.pr_type] ?? 9) - (PR_TYPE_ORDER[b.pr_type] ?? 9));
  }
  result.sort((a, b) => b.latest.localeCompare(a.latest));
  return result;
}

/** Display a PR value in the user's unit — weight PRs are stored in kg (docs/02). */
function displayValue(pr: Pr, unit: UnitPref): string {
  return formatPrValue(pr.value, pr.unit === "kg" ? unit : pr.unit);
}

/** The Dashboard's personal-records grid: a card per exercise with its illustration + records. */
export function PrList({ prs, unit }: { prs: Pr[]; unit: UnitPref }) {
  const groups = groupByExercise(prs);
  return (
    <Stagger className={styles.grid} step={26} max={10}>
      {groups.map((group) => (
        <Link key={group.exerciseId} href={`/library/${group.slug}`} className={styles.card}>
          <IllustrationImage
            url={group.illustrationUrl}
            status={group.illustrationStatus}
            name={group.name}
          />
          <div className={styles.body}>
            <div className={styles.head}>
              <h3 className={styles.name}>{group.name}</h3>
              {group.isCustom && <Badge tone="custom">Custom</Badge>}
            </div>
            <dl className={styles.records}>
              {group.prs.map((pr) => (
                <div key={pr.id} className={styles.record}>
                  <dt className={styles.recordLabel}>{prTypeLabel(pr.pr_type)}</dt>
                  <dd className={`${styles.recordValue} tnum`}>{displayValue(pr, unit)}</dd>
                </div>
              ))}
            </dl>
            <p className={styles.since}>
              Latest <LocalTime iso={group.latest} format="relative" />
            </p>
          </div>
        </Link>
      ))}
    </Stagger>
  );
}
