"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { cn } from "@/lib/cn";
import { ClientApiError, NetworkError, updatePreferences } from "@/lib/client";
import type { UnitPref } from "@/lib/types";
import styles from "./UnitToggle.module.css";

const UNITS: { value: UnitPref; label: string }[] = [
  { value: "kg", label: "Kilograms" },
  { value: "lb", label: "Pounds" },
];

/**
 * The weight-unit preference (Settings → units, docs/07). Optimistic: the toggle flips instantly,
 * then persists via `PATCH /api/me` and `router.refresh()`es so server-rendered weights re-format;
 * a failed write reverts and surfaces the error. Weights are stored in kg — this is display-only.
 */
export function UnitToggle({ current }: { current: UnitPref }) {
  const router = useRouter();
  const [unit, setUnit] = useState<UnitPref>(current);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const choose = async (next: UnitPref) => {
    if (next === unit || saving) return;
    const previous = unit;
    setUnit(next);
    setError(null);
    setSaving(true);
    try {
      await updatePreferences({ unit_pref: next });
      router.refresh();
    } catch (caught) {
      setUnit(previous);
      if (caught instanceof NetworkError) {
        setError("You appear to be offline — preference not saved.");
      } else if (caught instanceof ClientApiError) {
        setError(caught.message);
      } else {
        throw caught;
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.group} role="group" aria-label="Weight unit">
        {UNITS.map((option) => (
          <button
            key={option.value}
            type="button"
            className={cn(styles.option, option.value === unit && styles.active)}
            aria-pressed={option.value === unit}
            disabled={saving}
            onClick={() => choose(option.value)}
          >
            {option.label}
            <span className={styles.abbr}>{option.value}</span>
          </button>
        ))}
      </div>
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
