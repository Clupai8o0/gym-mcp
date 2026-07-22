import Link from "next/link";
import type { Metadata } from "next";

import {
  DashboardTabs,
  FrequencyHeatmap,
  PrList,
  RangeControl,
  VolumeChart,
} from "@/components/dashboard";
import { Button, EmptyState } from "@/components/ui";
import { getFrequency, getVolume, listPrs } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { DEFAULT_RANGE_KEY, rangeWindow, resolveRange } from "@/lib/ranges";
import type { UnitPref } from "@/lib/types";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Dashboard",
  description: "Personal records, training volume, and session frequency.",
};

type RawParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<RawParams>;
}) {
  const params = await searchParams;
  const range = resolveRange(one(params.range) || DEFAULT_RANGE_KEY);
  const { from, to } = rangeWindow(range);

  const [me, prs, volume, frequency] = await Promise.all([
    requireUser("/dashboard"),
    listPrs(),
    getVolume(from, to),
    getFrequency(range.weeks),
  ]);
  const unit = me.unit_pref as UnitPref;
  const hasVolume = volume.items.length > 0;

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <div className={styles.titleBlock}>
          <p className="eyebrow">Progress</p>
          <h1 className={styles.title}>Dashboard</h1>
        </div>
        <RangeControl current={range.key} />
      </header>

      <DashboardTabs />

      <section className={styles.section} aria-labelledby="prs-heading">
        <div className={styles.sectionHead}>
          <h2 id="prs-heading" className={styles.sectionTitle}>
            Personal records
          </h2>
        </div>
        {prs.items.length > 0 ? (
          <PrList prs={prs.items} unit={unit} />
        ) : (
          <EmptyState
            title="No personal records yet"
            description="Log a few sets and your best lifts and holds will show up here, each with its illustration."
            action={
              <Link href="/log">
                <Button variant="primary">Log a workout</Button>
              </Link>
            }
          />
        )}
      </section>

      <section className={styles.section} aria-labelledby="volume-heading">
        <div className={styles.sectionHead}>
          <h2 id="volume-heading" className={styles.sectionTitle}>
            Volume
          </h2>
          <span className={styles.sectionMeta}>Last {range.label}</span>
        </div>
        {hasVolume ? (
          <VolumeChart volume={volume} unit={unit} />
        ) : (
          <p className={styles.empty}>No sets logged in this range yet.</p>
        )}
      </section>

      <section className={styles.section} aria-labelledby="frequency-heading">
        <div className={styles.sectionHead}>
          <h2 id="frequency-heading" className={styles.sectionTitle}>
            Frequency
          </h2>
          <span className={styles.sectionMeta}>Last {range.weeks} weeks</span>
        </div>
        <FrequencyHeatmap frequency={frequency} />
      </section>
    </div>
  );
}
