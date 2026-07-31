"use client";

import { useHydrated } from "@/lib/hydration";
import { formatDate, formatRelativeDate, formatTime } from "@/lib/format";

const FORMATTERS = {
  date: formatDate,
  time: formatTime,
  relative: formatRelativeDate,
} as const;

export interface LocalTimeProps {
  /** ISO-8601 instant from the API. */
  iso: string;
  /** `date` → "Jul 7, 2026" · `time` → "5:46 PM" · `relative` → "Today" / "3 days ago". */
  format?: keyof typeof FORMATTERS;
  className?: string;
}

/**
 * Renders an instant in the **viewer's** timezone.
 *
 * A server render cannot know that timezone, so it emits the UTC reading (stable everywhere,
 * no layout shift, and `dateTime` is always exact) and this corrects it to local on mount.
 * `suppressHydrationWarning` covers the one frame where the two legitimately differ — the
 * alternative was the live hydration error the old `toLocaleDateString(undefined, …)` threw
 * on `/settings` and `/log/[id]`, which regenerated the whole authed subtree on the client.
 */
export function LocalTime({ iso, format = "date", className }: LocalTimeProps) {
  const render = FORMATTERS[format];
  const hydrated = useHydrated();

  return (
    <time dateTime={iso} className={className} suppressHydrationWarning>
      {render(iso, hydrated ? "local" : "utc")}
    </time>
  );
}
