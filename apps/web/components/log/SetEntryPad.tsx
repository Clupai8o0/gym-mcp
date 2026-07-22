"use client";

import { useState } from "react";

import { Button } from "@/components/ui";
import type { UnitPref } from "@/lib/types";
import { NumberField } from "./NumberField";
import type { SetDraft } from "./types";
import styles from "./SetEntryPad.module.css";

export interface SetEntryPadProps {
  draft: SetDraft;
  onChange: (draft: SetDraft) => void;
  onLog: () => void;
  unitPref: UnitPref;
  /** Disables the pad while a save is mid-flight (still allows queued offline logs). */
  busy?: boolean;
  /** Next set number, shown on the log button so entry feels sequential. */
  setNumber: number;
}

/**
 * The core logging interaction (docs/07 §SetEntryPad): fast, one-handed numeric entry for a set.
 * Weight+reps by default; a timed-hold mode swaps reps for seconds (isometrics); RPE is opt-in to
 * keep the common path minimal. The draft is controlled by the parent so the previous set can
 * pre-fill the next (docs/07). Optimistic save is handled upstream.
 */
export function SetEntryPad({
  draft,
  onChange,
  onLog,
  unitPref,
  busy = false,
  setNumber,
}: SetEntryPadProps) {
  const [holdMode, setHoldMode] = useState(draft.holdSeconds != null);
  const [showRpe, setShowRpe] = useState(draft.rpe != null);

  const set = (patch: Partial<SetDraft>) => onChange({ ...draft, ...patch });

  const enterHold = () => {
    setHoldMode(true);
    set({ reps: null });
  };
  const enterReps = () => {
    setHoldMode(false);
    set({ holdSeconds: null });
  };

  const hasMetric = draft.weightKg != null || draft.reps != null || draft.holdSeconds != null;

  return (
    <div className={styles.pad}>
      <div className={styles.modes} role="group" aria-label="Set type">
        <button
          type="button"
          className={styles.mode}
          aria-pressed={!holdMode}
          onClick={enterReps}
        >
          Reps
        </button>
        <button
          type="button"
          className={styles.mode}
          aria-pressed={holdMode}
          onClick={enterHold}
        >
          Hold
        </button>
      </div>

      <div className={styles.fields}>
        <NumberField
          label="Weight"
          value={draft.weightKg}
          onChange={(v) => set({ weightKg: v })}
          step={2.5}
          decimal
          suffix={unitPref}
        />
        {holdMode ? (
          <NumberField
            label="Hold"
            value={draft.holdSeconds}
            onChange={(v) => set({ holdSeconds: v })}
            step={5}
            suffix="s"
          />
        ) : (
          <NumberField
            label="Reps"
            value={draft.reps}
            onChange={(v) => set({ reps: v })}
            step={1}
          />
        )}
        {showRpe && (
          <NumberField
            label="RPE"
            value={draft.rpe}
            onChange={(v) => set({ rpe: v })}
            step={0.5}
            decimal
            min={1}
            max={10}
          />
        )}
      </div>

      <div className={styles.actions}>
        {!showRpe && (
          <Button variant="ghost" size="sm" onClick={() => setShowRpe(true)}>
            + RPE
          </Button>
        )}
        <Button
          variant="primary"
          className={styles.logButton}
          onClick={onLog}
          disabled={!hasMetric}
          loading={busy}
        >
          Log set {setNumber}
        </Button>
      </div>
    </div>
  );
}
