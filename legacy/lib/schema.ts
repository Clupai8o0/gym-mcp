import { z } from "zod";

export const SESSION_TYPES = [
  "upper_power",
  "lower_power",
  "skill_rings",
  "upper_hypertrophy",
  "lower_hypertrophy",
  "custom",
] as const;

export const PR_TYPES = ["weight", "reps", "hold_time"] as const;
export const PR_TYPES_WITH_FIRST = [...PR_TYPES, "first_log"] as const;

export const sessionTypeSchema = z.enum(SESSION_TYPES);
export const prTypeSchema = z.enum(PR_TYPES);

export const isoDateSchema = z
  .string()
  .refine((v) => !isNaN(Date.parse(v)), "Must be an ISO 8601 date string");

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------
export const logSessionInput = {
  session_type: sessionTypeSchema,
  date: isoDateSchema,
  notes: z.string().optional(),
  duration_minutes: z.number().int().positive().optional(),
};

export const getSessionInput = {
  session_id: z.string().uuid(),
};

export const listSessionsInput = {
  session_type: sessionTypeSchema.optional(),
  from_date: isoDateSchema.optional(),
  to_date: isoDateSchema.optional(),
  limit: z.number().int().positive().max(100).optional(),
  offset: z.number().int().min(0).optional(),
};

// ---------------------------------------------------------------------------
// Sets
// ---------------------------------------------------------------------------
export const logSetInput = {
  session_id: z.string().uuid(),
  exercise_name: z.string().min(1),
  set_number: z.number().int().positive(),
  weight_kg: z.number().nonnegative().optional(),
  reps: z.number().int().nonnegative().optional(),
  hold_seconds: z.number().int().nonnegative().optional(),
  rpe: z.number().min(1).max(10).optional(),
  notes: z.string().optional(),
};

export const getSessionSetsInput = {
  session_id: z.string().uuid(),
};

// ---------------------------------------------------------------------------
// PRs
// ---------------------------------------------------------------------------
export const getPrsInput = {
  exercise_name: z.string().optional(),
};

export const getPrHistoryInput = {
  exercise_name: z.string().min(1),
  pr_type: prTypeSchema,
};

export const logPrInput = {
  exercise_name: z.string().min(1),
  pr_type: prTypeSchema,
  value: z.number(),
  achieved_at: isoDateSchema,
  session_id: z.string().uuid().optional(),
  notes: z.string().optional(),
};

// ---------------------------------------------------------------------------
// Skills
// ---------------------------------------------------------------------------
export const updateSkillProgressInput = {
  skill_name: z.string().min(1),
  current_stage: z.number().int().min(0),
  stage_name: z.string().min(1),
  progress_percent: z.number().int().min(0).max(100),
  notes: z.string().optional(),
};

export const getSkillDetailInput = {
  skill_name: z.string().min(1),
};

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------
export const getVolumeSummaryInput = {
  from_date: isoDateSchema,
  to_date: isoDateSchema,
  exercise_name: z.string().optional(),
};

export const getSessionFrequencyInput = {
  weeks: z.number().int().positive().max(104).optional(),
};
