import type { Metadata } from "next";

import { FrequencyHeatmap } from "@/components/dashboard/FrequencyHeatmap";
import { RangeControl } from "@/components/dashboard/RangeControl";
import { getFrequency } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { DEFAULT_RANGE_KEY, resolveRange } from "@/lib/ranges";
import styles from "../progress.module.css";

export const metadata: Metadata = {
  title: "Frequency",
  description: "How often you train, week by week.",
};

type RawParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

/** Sessions per ISO week, at a cell size you can actually read (Phase 11C). */
export default async function FrequencyPage({
  searchParams,
}: {
  searchParams: Promise<RawParams>;
}) {
  const params = await searchParams;
  const range = resolveRange(one(params.range) || DEFAULT_RANGE_KEY);

  const [, frequency] = await Promise.all([
    requireUser("/progress/frequency"),
    getFrequency(range.weeks),
  ]);

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <div className={styles.titleBlock}>
          <p className="eyebrow">Progress</p>
          <h1 className={styles.title}>Frequency</h1>
          <p className={styles.lede}>
            One cell per week, Monday-anchored. Consistency is the thing that compounds.
          </p>
        </div>
        <RangeControl current={range.key} />
      </header>

      <FrequencyHeatmap frequency={frequency} size="lg" />
    </div>
  );
}
