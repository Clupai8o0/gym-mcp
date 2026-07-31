import Link from "next/link";

import { SessionStarter } from "@/components/log";
import { Button, Card } from "@/components/ui";
import styles from "./HomeWelcome.module.css";

/**
 * What a brand-new account sees (Phase 11C). The dashboard is now the front door, so the first
 * impression can't be three empty chart boxes: there is nothing to count yet, so this offers the
 * only two things that actually exist — start training, or go look at what you could train.
 * Stats, strips and records appear on their own once there is a single session behind them.
 */
export function HomeWelcome({ exerciseCount }: { exerciseCount: number }) {
  return (
    <Card padded className={styles.card}>
      <p className="eyebrow">Welcome to Tempo</p>
      <h2 className={styles.title}>Your first workout starts here.</h2>
      <p className={styles.lede}>
        Log a session and this screen fills in — your week, your records, your streak.
      </p>
      <div className={styles.actions}>
        <SessionStarter compact label="Start your first workout" variant="primary" />
        <Link href="/library">
          <Button variant="outline">
            Browse {exerciseCount > 0 ? exerciseCount.toLocaleString() : ""} exercises
          </Button>
        </Link>
      </div>
    </Card>
  );
}
