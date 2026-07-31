import type { Metadata } from "next";

import { RangeControl, VolumeChart } from "@/components/dashboard";
import { getVolume } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { DEFAULT_RANGE_KEY, rangeWindow, resolveRange } from "@/lib/ranges";
import type { UnitPref } from "@/lib/types";
import styles from "../progress.module.css";

export const metadata: Metadata = {
  title: "Volume",
  description: "Sets, reps, and tonnage over time.",
};

type RawParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

/**
 * Training volume over a selectable range (Phase 11C).
 *
 * The `RangeControl` lives **here**, with the only data it actually governs. On the old combined
 * dashboard it sat above the records grid, which is all-time — so it read as broken.
 */
export default async function VolumePage({ searchParams }: { searchParams: Promise<RawParams> }) {
  const params = await searchParams;
  const range = resolveRange(one(params.range) || DEFAULT_RANGE_KEY);
  const { from, to } = rangeWindow(range);

  const [me, volume] = await Promise.all([requireUser("/progress/volume"), getVolume(from, to)]);
  const unit = me.unit_pref as UnitPref;

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <div className={styles.titleBlock}>
          <p className="eyebrow">Progress</p>
          <h1 className={styles.title}>Volume</h1>
          <p className={styles.lede}>
            Sets, reps, and tonnage over the selected window, and the movements you spent them on.
          </p>
        </div>
        <RangeControl current={range.key} />
      </header>

      {volume.items.length > 0 ? (
        <VolumeChart volume={volume} unit={unit} />
      ) : (
        <p className={styles.empty}>No sets logged in this range yet.</p>
      )}
    </div>
  );
}
