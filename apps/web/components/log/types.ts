/**
 * Client-side view model for the active-session logger (Phase 7). The server's `SessionDetail`
 * seeds this; the logger then evolves it locally with optimistic + queued writes. Kept separate
 * from the API contract types (`lib/types`) because a UI set carries transient status the server
 * doesn't (client id, saving/queued/error) alongside the persisted fields.
 */
import type { Exercise } from "@/lib/types";

export type SetStatus = "saved" | "saving" | "queued" | "error";

export interface LogSet {
  /** Stable UI identity (also the offline-queue key); present before the server assigns an id. */
  clientId: string;
  /** Server `exercise_sets.id`, once the write lands (null while saving/queued). */
  serverId: string | null;
  setNumber: number;
  weightKg: number | null;
  reps: number | null;
  holdSeconds: number | null;
  rpe: number | null;
  status: SetStatus;
  isPr: boolean;
  prType: string | null;
  /** New PR value from the server verdict — drives the count-up celebration. */
  prValue: number | null;
  prUnit: string | null;
  errorMessage?: string;
}

export interface LogGroup {
  exercise: Exercise;
  sets: LogSet[];
}

/** Draft metrics from the entry pad, before a set id/status exists. */
export interface SetDraft {
  weightKg: number | null;
  reps: number | null;
  holdSeconds: number | null;
  rpe: number | null;
}
