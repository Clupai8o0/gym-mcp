import Link from "next/link";
import type { Metadata } from "next";

import { PrList } from "@/components/dashboard/PrList";
import { Button, EmptyState } from "@/components/ui";
import { listPrs } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import type { UnitPref } from "@/lib/types";
import styles from "../progress.module.css";

export const metadata: Metadata = {
  title: "Records",
  description: "Every personal record you hold, with its illustration.",
};

/**
 * Personal records — all-time, one card per exercise (Phase 11C).
 *
 * Deliberately **no range control**: `listPrs()` takes no window, so a control here would be a
 * lie. Time-bounded questions live on `/progress/volume`.
 */
export default async function RecordsPage() {
  const [me, prs] = await Promise.all([requireUser("/progress/records"), listPrs()]);
  const unit = me.unit_pref as UnitPref;

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <div className={styles.titleBlock}>
          <p className="eyebrow">Progress</p>
          <h1 className={styles.title}>Records</h1>
          <p className={styles.lede}>
            Your best lift, longest hold, and highest rep count for every movement you&rsquo;ve
            trained. All-time, freshest first.
          </p>
        </div>
      </header>

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
    </div>
  );
}
