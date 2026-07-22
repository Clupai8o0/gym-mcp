"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { cn } from "@/lib/cn";
import { DASHBOARD_RANGES } from "@/lib/ranges";
import styles from "./RangeControl.module.css";

/**
 * Segmented control for the dashboard time range (docs/07 §Dashboard). Writes `?range=` to the
 * URL so the server re-renders both charts against the new window (shareable + back-button), like
 * the Library filters. A `useTransition` keeps the control responsive while the server data streams.
 */
export function RangeControl({ current }: { current: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  const select = (key: string) => {
    if (key === current) return;
    startTransition(() => router.push(`/dashboard?range=${key}`, { scroll: false }));
  };

  return (
    <div className={styles.group} role="group" aria-label="Time range" aria-busy={pending}>
      {DASHBOARD_RANGES.map((range) => {
        const active = range.key === current;
        return (
          <button
            key={range.key}
            type="button"
            className={cn(styles.option, active && styles.active)}
            aria-pressed={active}
            onClick={() => select(range.key)}
          >
            {range.label}
          </button>
        );
      })}
    </div>
  );
}
