"use client";

import { useState } from "react";
import Link from "next/link";

import { Badge } from "@/components/ui";
import { titleCase } from "@/lib/format";
import type { UnitPref } from "@/lib/types";
import { SetEntryPad } from "./SetEntryPad";
import { SetRow } from "./SetRow";
import type { LogGroup, LogSet, SetDraft } from "./types";
import styles from "./ExerciseBlock.module.css";

export interface ExerciseBlockProps {
  group: LogGroup;
  unitPref: UnitPref;
  /** Client id of the set to play the PR bloom for (cleared shortly after by the parent). */
  celebrateId: string | null;
  onLog: (exerciseId: string, draft: SetDraft) => void;
  onDeleteSet: (clientId: string) => void;
  onRetrySet: (clientId: string) => void;
  onRemove: (exerciseId: string) => void;
}

const EMPTY_DRAFT: SetDraft = { weightKg: null, reps: null, holdSeconds: null, rpe: null };

/** Seed the next set's draft from the previous set (docs/07: previous set pre-fills the next). */
function prefillFrom(set: LogSet | undefined): SetDraft {
  if (!set) return EMPTY_DRAFT;
  return { weightKg: set.weightKg, reps: set.reps, holdSeconds: set.holdSeconds, rpe: null };
}

/**
 * One exercise within the active session: its header, logged sets, and the entry pad. Owns the
 * pad's draft so the previous set pre-fills the next (re-seeded whenever a new set lands). Logging
 * itself is orchestrated by `SessionLogger` (which holds the offline queue).
 */
export function ExerciseBlock({
  group,
  unitPref,
  celebrateId,
  onLog,
  onDeleteSet,
  onRetrySet,
  onRemove,
}: ExerciseBlockProps) {
  const { exercise, sets } = group;

  // Prefill from the most recent non-errored set; re-seed when that set changes identity.
  const lastSet = [...sets].reverse().find((s) => s.status !== "error");
  const lastId = lastSet?.clientId ?? null;
  const [seededFrom, setSeededFrom] = useState<string | null>(lastId);
  const [draft, setDraft] = useState<SetDraft>(() => prefillFrom(lastSet));
  if (lastId !== seededFrom) {
    setSeededFrom(lastId);
    setDraft(prefillFrom(lastSet));
  }

  // Next set number = highest logged + 1 (not count+1), so it never collides after a delete.
  const nextNumber =
    sets.filter((s) => s.status !== "error").reduce((max, s) => Math.max(max, s.setNumber), 0) + 1;
  const primaryMuscle = exercise.primary_muscles[0];

  const handleLog = () => {
    onLog(exercise.id, draft);
  };

  return (
    <section className={styles.block} aria-label={exercise.name}>
      <header className={styles.header}>
        <div className={styles.heading}>
          <Link href={`/library/${exercise.slug}`} className={styles.name} prefetch={false}>
            {exercise.name}
          </Link>
          <div className={styles.tags}>
            {primaryMuscle && <Badge tone="muscle">{titleCase(primaryMuscle)}</Badge>}
            {exercise.equipment && <Badge>{titleCase(exercise.equipment)}</Badge>}
          </div>
        </div>
        {sets.length === 0 && (
          <button
            type="button"
            className={styles.remove}
            onClick={() => onRemove(exercise.id)}
          >
            Remove
          </button>
        )}
      </header>

      {sets.length > 0 && (
        <ul className={styles.sets}>
          {sets.map((set) => (
            <SetRow
              key={set.clientId}
              set={set}
              unitPref={unitPref}
              celebrate={set.clientId === celebrateId}
              onDelete={() => onDeleteSet(set.clientId)}
              onRetry={() => onRetrySet(set.clientId)}
            />
          ))}
        </ul>
      )}

      <SetEntryPad
        draft={draft}
        onChange={setDraft}
        onLog={handleLog}
        unitPref={unitPref}
        setNumber={nextNumber}
      />
    </section>
  );
}
