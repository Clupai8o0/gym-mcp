/**
 * Display formatting — kg/lb, muscle/equipment labels, dates. Pure functions, no domain logic
 * (weights are stored in kg; lb is a display-only conversion — docs/02).
 */
import type { UnitPref } from "./types";

const KG_PER_LB = 0.45359237;

export function kgToLb(kg: number): number {
  return kg / KG_PER_LB;
}

/** Format a kg weight in the user's preferred unit with a sensible precision. */
export function formatWeight(kg: number, unit: "kg" | "lb" = "kg"): string {
  const value = unit === "lb" ? kgToLb(kg) : kg;
  const rounded = Math.round(value * 10) / 10;
  const text = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
  return `${text} ${unit}`;
}

/** A whole-number tonnage in the user's unit, grouped ("1,050 kg") — for volume totals. */
export function formatTonnage(kg: number, unit: UnitPref = "kg"): string {
  const value = unit === "lb" ? kgToLb(kg) : kg;
  return `${Math.round(value).toLocaleString()} ${unit}`;
}

/** Group a count with thousands separators ("1,204"). */
export function formatCount(n: number): string {
  return Math.round(n).toLocaleString();
}

/** A "Jul 7" label for an ISO **date** (YYYY-MM-DD), parsed as local to avoid TZ drift. */
export function formatWeekLabel(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

/** A PR value + its unit → a display string (unit is one of 'kg' | 'reps' | 's'). */
export function formatPrValue(value: number, unit: string): string {
  if (unit === "reps") {
    return `${Math.round(value)} reps`;
  }
  if (unit === "s") {
    return `${Math.round(value)}s`;
  }
  return formatWeight(value, unit === "lb" ? "lb" : "kg");
}

const PR_TYPE_LABELS: Record<string, string> = {
  weight: "Heaviest",
  reps: "Most reps",
  hold_time: "Longest hold",
  first_log: "First logged",
};

export function prTypeLabel(prType: string): string {
  return PR_TYPE_LABELS[prType] ?? titleCase(prType.replace(/_/g, " "));
}

/** Title-case a lower-case catalog token ("olympic weightlifting" → "Olympic Weightlifting"). */
export function titleCase(value: string): string {
  return value.replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

const DAY_MS = 86_400_000;

/** Start-of-day for a date, in the viewer's local timezone. */
function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/** "Today" / "Yesterday" / a short date — for session headers (docs/07 §Log). */
export function formatRelativeDate(iso: string): string {
  const then = new Date(iso);
  const days = Math.round((startOfDay(new Date()) - startOfDay(then)) / DAY_MS);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days > 1 && days < 7) return `${days} days ago`;
  return formatDate(iso);
}

/** True when the ISO timestamp falls on the viewer's current local day. */
export function isToday(iso: string): boolean {
  return startOfDay(new Date(iso)) === startOfDay(new Date());
}

/** A short "3:24 PM"-style time for a session/set timestamp. */
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** Whole-minute duration → "45 min" / "1 h 05 min". */
export function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0 ? `${h} h` : `${h} h ${String(m).padStart(2, "0")} min`;
}

/** Seconds → a compact "1:05" mm:ss clock (rest timer, holds). */
export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

/** A one-line summary of a set's metrics ("80 kg × 5", "45s hold", "12 reps"). */
export function formatSetSummary(
  set: { weight_kg: number | null; reps: number | null; hold_seconds: number | null },
  unit: UnitPref = "kg",
): string {
  if (set.hold_seconds != null) {
    const base = `${set.hold_seconds}s`;
    return set.weight_kg != null
      ? `${formatWeight(set.weight_kg, unit)} · ${base} hold`
      : `${base} hold`;
  }
  if (set.weight_kg != null && set.reps != null) {
    return `${formatWeight(set.weight_kg, unit)} × ${set.reps}`;
  }
  if (set.weight_kg != null) return formatWeight(set.weight_kg, unit);
  if (set.reps != null) return `${set.reps} reps`;
  return "—";
}
