"use client";

import { useEffect, useState } from "react";

import { Badge, Button, Input, Spinner } from "@/components/ui";
import { Sheet } from "@/components/motion/Sheet";
import { searchExercises } from "@/lib/client";
import { titleCase } from "@/lib/format";
import type { Exercise } from "@/lib/types";
import styles from "./ExercisePicker.module.css";

export interface ExercisePickerProps {
  open: boolean;
  onClose: () => void;
  onAdd: (exercise: Exercise) => void;
  /** Exercise ids already in the session — shown as added, not re-addable. */
  addedIds: ReadonlySet<string>;
}

const DEBOUNCE_MS = 250;

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
      <path d="m20 20-3-3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

/**
 * Adds an exercise to the active session (docs/07 §Log). A bottom `Sheet` with debounced catalog
 * search (client fetch to the same `exercises.list` service REST/MCP use). Empty query returns the
 * catalog's first page so the picker is useful before typing.
 */
export function ExercisePicker({ open, onClose, onAdd, addedIds }: ExercisePickerProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Exercise[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      setFailed(false);
      searchExercises(query, controller.signal)
        .then((list) => setResults(list.items))
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") return;
          setFailed(true);
          setResults([]);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, open]);

  const pick = (exercise: Exercise) => {
    if (addedIds.has(exercise.id)) return;
    onAdd(exercise);
  };

  return (
    <Sheet open={open} onClose={onClose} label="Add an exercise">
      <div className={styles.head}>
        <h2 className={styles.title}>Add exercise</h2>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Done
        </Button>
      </div>

      <Input
        type="search"
        inputMode="search"
        autoFocus
        aria-label="Search the exercise catalog"
        placeholder="Search exercises…"
        leading={<SearchIcon />}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className={styles.search}
      />

      <div className={styles.results} aria-label="Search results">
        {loading ? (
          <div className={styles.state}>
            <Spinner />
          </div>
        ) : failed ? (
          <p className={styles.state}>Couldn’t reach the catalog. Check your connection.</p>
        ) : results.length === 0 ? (
          <p className={styles.state}>No exercises match “{query}”.</p>
        ) : (
          <ul className={styles.list}>
            {results.map((exercise) => {
              const added = addedIds.has(exercise.id);
              return (
                <li key={exercise.id}>
                  <button
                    type="button"
                    className={styles.result}
                    onClick={() => pick(exercise)}
                    disabled={added}
                    aria-label={added ? `${exercise.name}, already added` : `Add ${exercise.name}`}
                  >
                    <span className={styles.resultName}>{exercise.name}</span>
                    <span className={styles.resultMeta}>
                      {exercise.primary_muscles[0] && (
                        <Badge tone="muscle">{titleCase(exercise.primary_muscles[0])}</Badge>
                      )}
                      {exercise.equipment && <Badge>{titleCase(exercise.equipment)}</Badge>}
                    </span>
                    <span className={styles.action} aria-hidden>
                      {added ? "Added" : "+"}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Sheet>
  );
}
