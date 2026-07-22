/**
 * Display formatting — kg/lb, muscle/equipment labels, dates. Pure functions, no domain logic
 * (weights are stored in kg; lb is a display-only conversion — docs/02).
 */
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
