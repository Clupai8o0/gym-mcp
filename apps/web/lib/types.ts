/**
 * Convenience aliases over the generated OpenAPI types (`api-types.ts`, produced by
 * `pnpm gen:api` from the FastAPI schema). App code imports these names, never `any` — the
 * contract can't silently drift from the backend (docs/07 DoD).
 */
import type { components } from "./api-types";

export type Exercise = components["schemas"]["ExerciseOut"];
export type ExerciseDetail = components["schemas"]["ExerciseDetailOut"];
export type ExerciseList = components["schemas"]["ExerciseListOut"];
export type Pr = components["schemas"]["PrOut"];
export type PrList = components["schemas"]["PrListOut"];
export type Me = components["schemas"]["MeOut"];

/** `exercises.illustration_status` values (docs/02). */
export type IllustrationStatus = "pending" | "generating" | "ready" | "failed";
