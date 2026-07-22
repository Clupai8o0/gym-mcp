/**
 * Catalog filter vocabulary. Category/level are the enum values from the `exercises` CHECK
 * constraints (docs/02); muscle/equipment are the stable free-text vocabulary of the pinned
 * free-exercise-db dataset (docs/06). Reference data, not business logic — the server still
 * validates every filter against the DB.
 */
import type { SelectOption } from "@/components/ui";
import { titleCase } from "./format";

const asOptions = (values: string[]): SelectOption[] =>
  values.map((value) => ({ value, label: titleCase(value) }));

export const MUSCLES = asOptions([
  "abdominals",
  "abductors",
  "adductors",
  "biceps",
  "calves",
  "chest",
  "forearms",
  "glutes",
  "hamstrings",
  "lats",
  "lower back",
  "middle back",
  "neck",
  "quadriceps",
  "shoulders",
  "traps",
  "triceps",
]);

export const EQUIPMENT = asOptions([
  "barbell",
  "dumbbell",
  "cable",
  "machine",
  "kettlebells",
  "bands",
  "body only",
  "medicine ball",
  "exercise ball",
  "foam roll",
  "e-z curl bar",
  "other",
]);

export const CATEGORIES = asOptions([
  "strength",
  "stretching",
  "plyometrics",
  "powerlifting",
  "olympic weightlifting",
  "strongman",
  "cardio",
]);

export const LEVELS = asOptions(["beginner", "intermediate", "expert"]);

/** The filter keys the Library reflects in the URL (docs/07 §Library). */
export const FILTER_KEYS = ["q", "muscle", "equipment", "category", "level"] as const;
export type FilterKey = (typeof FILTER_KEYS)[number];
