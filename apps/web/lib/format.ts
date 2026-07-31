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

/**
 * A whole-number tonnage in the user's unit, grouped ("1,050 kg") — for volume totals.
 * `withUnit: false` returns just the number, for callers that render the unit separately.
 */
export function formatTonnage(
  kg: number,
  unit: UnitPref = "kg",
  { withUnit = true }: { withUnit?: boolean } = {},
): string {
  const value = unit === "lb" ? kgToLb(kg) : kg;
  const number = Math.round(value).toLocaleString();
  return withUnit ? `${number} ${unit}` : number;
}

/** Group a count with thousands separators ("1,204"). */
export function formatCount(n: number): string {
  return Math.round(n).toLocaleString();
}

/*
 * ── Dates & times ──────────────────────────────────────────────────────────────────────
 * These are written out by hand instead of via `Intl`. `toLocaleDateString(undefined, …)`
 * resolves a *different* locale on the server (Node's) than in the browser (the user's),
 * and even for one locale Node's and Chrome's ICU disagree on details like "pm" vs "PM" —
 * which surfaced as a live hydration error on `/settings` and `/log/[id]`. Hand-rolled
 * output depends on nothing but the Date's field accessors, so the only remaining variable
 * is the **timezone**, and that is what `zone` (and `<LocalTime>`) exist to control.
 */
const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

/**
 * Which clock to read a timestamp against. `"local"` is the viewer's — correct, but only
 * knowable in the browser. `"utc"` is stable everywhere, so it is what a server render emits
 * before {@link "@/components/ui/LocalTime"} corrects it on mount.
 */
export type Zone = "local" | "utc";

interface Fields {
  year: number;
  month: number;
  day: number;
  hours: number;
  minutes: number;
}

function fields(date: Date, zone: Zone): Fields {
  return zone === "utc"
    ? {
        year: date.getUTCFullYear(),
        month: date.getUTCMonth(),
        day: date.getUTCDate(),
        hours: date.getUTCHours(),
        minutes: date.getUTCMinutes(),
      }
    : {
        year: date.getFullYear(),
        month: date.getMonth(),
        day: date.getDate(),
        hours: date.getHours(),
        minutes: date.getMinutes(),
      };
}

/** A "Jul 7" label for an ISO **date** (YYYY-MM-DD). Date-only, so no timezone is involved. */
export function formatWeekLabel(isoDate: string): string {
  const [, month, day] = isoDate.split("-").map(Number);
  return `${MONTHS[(month ?? 1) - 1]} ${day ?? 1}`;
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

const WEEKDAYS = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
] as const;

/** "Jul 7, 2026". */
export function formatDate(iso: string, zone: Zone = "local"): string {
  const { year, month, day } = fields(new Date(iso), zone);
  return `${MONTHS[month]} ${day}, ${year}`;
}

/** "Friday, Jul 31" — the home screen's date line. */
export function formatDayLabel(iso: string, zone: Zone = "local"): string {
  const date = new Date(iso);
  const { month, day } = fields(date, zone);
  const weekday = WEEKDAYS[zone === "utc" ? date.getUTCDay() : date.getDay()];
  return `${weekday}, ${MONTHS[month]} ${day}`;
}

/** Single-letter weekday initials, Sunday-first — the seven-day strip. */
export function weekdayInitial(dayOfWeek: number): string {
  return WEEKDAYS[dayOfWeek].slice(0, 1);
}

const DAY_MS = 86_400_000;

/** Start-of-day as a day index, so two instants can be compared by calendar day. */
function dayIndex(date: Date, zone: Zone): number {
  const { year, month, day } = fields(date, zone);
  return Date.UTC(year, month, day) / DAY_MS;
}

/** "Today" / "Yesterday" / a short date — for session headers (docs/07 §Log). */
export function formatRelativeDate(iso: string, zone: Zone = "local"): string {
  const days = dayIndex(new Date(), zone) - dayIndex(new Date(iso), zone);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days > 1 && days < 7) return `${days} days ago`;
  return formatDate(iso, zone);
}

/*
 * `isToday` used to live here and answered "is a workout in progress?" from a server
 * component — i.e. in the server's timezone. Phase 11A replaced it with the real lifecycle
 * flag (`getActiveSession()` / `ended_at IS NULL`); it is deliberately not re-exported so
 * the heuristic can't come back.
 */

/** A short "3:24 PM"-style time for a session/set timestamp. */
export function formatTime(iso: string, zone: Zone = "local"): string {
  const { hours, minutes } = fields(new Date(iso), zone);
  const suffix = hours < 12 ? "AM" : "PM";
  const hour12 = hours % 12 === 0 ? 12 : hours % 12;
  return `${hour12}:${String(minutes).padStart(2, "0")} ${suffix}`;
}

/** Elapsed seconds → a live "12:04" / "1:12:04" clock (the docked session bar). */
export function formatElapsed(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const seconds = s % 60;
  const mm = hours > 0 ? String(minutes).padStart(2, "0") : String(minutes);
  return `${hours > 0 ? `${hours}:` : ""}${mm}:${String(seconds).padStart(2, "0")}`;
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
