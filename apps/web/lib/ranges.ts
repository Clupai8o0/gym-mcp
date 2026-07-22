/**
 * Dashboard time ranges (docs/07 §Dashboard — "volume over a selectable range"). One control
 * drives both charts: `days` bounds the volume window; `weeks` sizes the frequency heatmap. The
 * selected range lives in the URL (`?range=90d`) so the dashboard is server-rendered + shareable,
 * like the Library filters.
 */
export interface DashboardRange {
  key: string;
  /** Short control label. */
  label: string;
  /** Volume window length in days. */
  days: number;
  /** Frequency heatmap length in ISO weeks (≤52, the API cap). */
  weeks: number;
}

const DEFAULT_RANGE: DashboardRange = { key: "90d", label: "3M", days: 90, weeks: 13 };

export const DASHBOARD_RANGES: DashboardRange[] = [
  { key: "30d", label: "30D", days: 30, weeks: 8 },
  DEFAULT_RANGE,
  { key: "6mo", label: "6M", days: 182, weeks: 26 },
  { key: "1y", label: "1Y", days: 365, weeks: 52 },
];

export const DEFAULT_RANGE_KEY = DEFAULT_RANGE.key;

/** Resolve a `?range=` value to a known range (falling back to the default). */
export function resolveRange(key: string | undefined): DashboardRange {
  return DASHBOARD_RANGES.find((range) => range.key === key) ?? DEFAULT_RANGE;
}

/** The `[from, to]` ISO instants for a range, ending now. */
export function rangeWindow(
  range: DashboardRange,
  now: Date = new Date(),
): {
  from: string;
  to: string;
} {
  const from = new Date(now.getTime() - range.days * 86_400_000);
  return { from: from.toISOString(), to: now.toISOString() };
}
