"use client";

import { useId } from "react";

import { cn } from "@/lib/cn";
import styles from "./NumberField.module.css";

export interface NumberFieldProps {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  /** Increment/decrement step for the ± buttons (kg often 2.5; reps/seconds 1). */
  step?: number;
  min?: number;
  max?: number;
  /** Allow fractional entry (weights); reps/seconds stay integer. */
  decimal?: boolean;
  /** Suffix shown inside the field ("kg", "reps", "s"). */
  suffix?: string;
  className?: string;
}

/**
 * A large, one-handed numeric field for mid-workout entry (docs/07 §SetEntryPad). Big touch
 * targets, tabular figures, ± steppers, and a numeric soft-keyboard. Empty renders as no value
 * (not 0) so an untouched field doesn't log a spurious metric.
 */
export function NumberField({
  label,
  value,
  onChange,
  step = 1,
  min = 0,
  max,
  decimal = false,
  suffix,
  className,
}: NumberFieldProps) {
  const id = useId();

  const clamp = (n: number): number => {
    let next = n;
    if (min != null) next = Math.max(min, next);
    if (max != null) next = Math.min(max, next);
    return decimal ? Math.round(next * 100) / 100 : Math.round(next);
  };

  const nudge = (delta: number) => {
    onChange(clamp((value ?? 0) + delta));
  };

  const onInput = (raw: string) => {
    if (raw === "") {
      onChange(null);
      return;
    }
    const parsed = decimal ? Number.parseFloat(raw) : Number.parseInt(raw, 10);
    if (Number.isNaN(parsed)) return;
    onChange(clamp(parsed));
  };

  return (
    <div className={cn(styles.field, className)}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      <div className={styles.control}>
        <button
          type="button"
          className={styles.step}
          onClick={() => nudge(-step)}
          disabled={value != null && min != null && value <= min}
          aria-label={`Decrease ${label}`}
        >
          −
        </button>
        <span className={styles.inputWrap}>
          <input
            id={id}
            className={`${styles.input} tnum`}
            type="text"
            inputMode={decimal ? "decimal" : "numeric"}
            pattern={decimal ? "[0-9]*[.,]?[0-9]*" : "[0-9]*"}
            value={value ?? ""}
            onChange={(e) => onInput(e.target.value)}
            placeholder="0"
            aria-describedby={suffix ? `${id}-suffix` : undefined}
          />
          {suffix && (
            <span id={`${id}-suffix`} className={styles.suffix} aria-hidden>
              {suffix}
            </span>
          )}
        </span>
        <button
          type="button"
          className={styles.step}
          onClick={() => nudge(step)}
          aria-label={`Increase ${label}`}
        >
          +
        </button>
      </div>
    </div>
  );
}
