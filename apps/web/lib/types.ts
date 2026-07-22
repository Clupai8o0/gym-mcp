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
export type MeUpdate = components["schemas"]["MeUpdate"];

/** Dashboard analytics + skills contracts (Phase 8). */
export type Volume = components["schemas"]["VolumeOut"];
export type VolumeItem = components["schemas"]["VolumeItem"];
export type Frequency = components["schemas"]["FrequencyOut"];
export type FrequencyItem = components["schemas"]["FrequencyItem"];
export type SkillsOverview = components["schemas"]["SkillsOverviewOut"];
export type SkillOverview = components["schemas"]["SkillOverviewItem"];
export type SkillDetail = components["schemas"]["SkillDetailOut"];
export type SkillProgress = components["schemas"]["SkillProgressOut"];
export type SkillProgressUpdate = components["schemas"]["SkillProgressUpsert"];

/** Settings → Connected apps (Phase 8). */
export type Connection = components["schemas"]["ConnectionOut"];
export type ConnectionList = components["schemas"]["ConnectionListOut"];
export type RevokeConnection = components["schemas"]["RevokeConnectionOut"];

/** Workout-log contracts (Phase 7). */
export type Session = components["schemas"]["SessionOut"];
export type SessionDetail = components["schemas"]["SessionDetailOut"];
export type SessionList = components["schemas"]["SessionListOut"];
export type SessionCreate = components["schemas"]["SessionCreate"];
export type ExerciseSetGroup = components["schemas"]["ExerciseSetGroup"];
export type WorkoutSet = components["schemas"]["SetOut"];
export type SetCreate = components["schemas"]["SetCreate"];
export type SetUpdate = components["schemas"]["SetUpdate"];
export type LoggedSet = components["schemas"]["LoggedSetOut"];
export type PrInfo = components["schemas"]["PrInfo"];

/** `exercises.illustration_status` values (docs/02). */
export type IllustrationStatus = "pending" | "generating" | "ready" | "failed";

/** `users.unit_pref` values (docs/02) — display-only; weights are stored in kg. */
export type UnitPref = "kg" | "lb";
