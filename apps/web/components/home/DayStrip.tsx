"use client";

import Link from "next/link";

import { weekdayInitial } from "@/lib/format";
import { useHydrated } from "@/lib/hydration";
import { cn } from "@/lib/cn";
import styles from "./DayStrip.module.css";

const DAY_MS = 86_400_000;
const DAYS = 7;

export interface DayStripProps {
  /** `performed_at` for every session in roughly the last nine days (a TZ-safe overshoot). */
  sessionDates: string[];
  /** The server's "now" — the strip ends today. */
  now: string;
}

interface Day {
  key: number;
  initial: string;
  count: number;
  today: boolean;
}

function dayKey(date: Date, local: boolean): number {
  return local
    ? Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / DAY_MS
    : Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()) / DAY_MS;
}

function build(sessionDates: string[], now: string, local: boolean): Day[] {
  const counts = new Map<number, number>();
  for (const iso of sessionDates) {
    const key = dayKey(new Date(iso), local);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const today = dayKey(new Date(now), local);
  return Array.from({ length: DAYS }, (_, index) => {
    const key = today - (DAYS - 1 - index);
    return {
      key,
      // `key` is days-since-epoch; 1970-01-01 was a Thursday, hence the +4.
      initial: weekdayInitial((key + 4) % 7),
      count: counts.get(key) ?? 0,
      today: key === today,
    };
  });
}

/**
 * Seven cells, one per day, ending today — the "am I actually showing up?" glance.
 *
 * Bucketing happens on the client because a calendar day only exists in a timezone: the server
 * would file a Monday-evening session in UTC−8 under Tuesday. The server render uses UTC so the
 * markup is stable, then this re-buckets locally on hydration (see `lib/hydration`).
 */
export function DayStrip({ sessionDates, now }: DayStripProps) {
  const hydrated = useHydrated();
  const days = build(sessionDates, now, hydrated);

  return (
    <Link href="/progress/frequency" className={styles.strip} aria-label="Last 7 days of training">
      {days.map((day, index) => (
        <span key={day.key} className={styles.day}>
          <span
            className={cn(
              styles.cell,
              "grow-y",
              day.count > 0 && styles.filled,
              day.today && styles.today,
            )}
            // 30ms apart — the week reads left to right instead of appearing at once (docs/08 §8).
            style={{ "--enter-delay": `${index * 30}ms` } as React.CSSProperties}
            aria-hidden
          />
          <span className={styles.initial}>{day.initial}</span>
        </span>
      ))}
      <span className="sr-only">
        {days.filter((day) => day.count > 0).length} of the last 7 days trained
      </span>
    </Link>
  );
}
