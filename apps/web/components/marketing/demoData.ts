/**
 * Sample training data for the marketing page's live dashboard preview.
 *
 * Shapes match the generated API types exactly, so `VolumeChart` and `FrequencyHeatmap` render
 * against it completely unmodified. The preview is therefore the real interface rather than a
 * screenshot, and it cannot drift from the product as the product changes.
 *
 * This is generated data describing one plausible half-year of general-gym training. The section
 * says so on the page.
 */
import type { Frequency, Volume } from "@/lib/types";

/** 26 Monday-anchored ISO weeks. */
const WEEK_STARTS = [
  "2026-02-02",
  "2026-02-09",
  "2026-02-16",
  "2026-02-23",
  "2026-03-02",
  "2026-03-09",
  "2026-03-16",
  "2026-03-23",
  "2026-03-30",
  "2026-04-06",
  "2026-04-13",
  "2026-04-20",
  "2026-04-27",
  "2026-05-04",
  "2026-05-11",
  "2026-05-18",
  "2026-05-25",
  "2026-06-01",
  "2026-06-08",
  "2026-06-15",
  "2026-06-22",
  "2026-06-29",
  "2026-07-06",
  "2026-07-13",
  "2026-07-20",
  "2026-07-27",
] as const;

/** Patchy in February, four a week by summer. Two weeks missed entirely, which is the point. */
const WEEK_COUNTS = [1, 2, 0, 2, 3, 2, 3, 1, 4, 3, 3, 2, 4, 3, 4, 2, 0, 3, 4, 4, 3, 4, 3, 4, 4, 3];

export const demoFrequency: Frequency = {
  weeks: WEEK_STARTS.length,
  items: WEEK_STARTS.map((week_start, i) => ({ week_start, count: WEEK_COUNTS[i] ?? 0 })),
};

export const demoVolume: Volume = {
  date_from: "2026-02-02T00:00:00Z",
  date_to: "2026-08-02T00:00:00Z",
  items: [
    {
      exercise_id: "11111111-1111-4111-8111-111111111111",
      exercise_name: "Barbell Bench Press",
      total_sets: 24,
      total_reps: 192,
      total_tonnage_kg: 14880,
    },
    {
      exercise_id: "22222222-2222-4222-8222-222222222222",
      exercise_name: "Back Squat",
      total_sets: 21,
      total_reps: 147,
      total_tonnage_kg: 18375,
    },
    {
      exercise_id: "33333333-3333-4333-8333-333333333333",
      exercise_name: "Pull-Up",
      total_sets: 20,
      total_reps: 164,
      // Bodyweight work carries no load, so the ranking runs on sets and tonnage stays null.
      total_tonnage_kg: null,
    },
    {
      exercise_id: "44444444-4444-4444-8444-444444444444",
      exercise_name: "Overhead Press",
      total_sets: 18,
      total_reps: 126,
      total_tonnage_kg: 6930,
    },
    {
      exercise_id: "55555555-5555-4555-8555-555555555555",
      exercise_name: "Barbell Row",
      total_sets: 16,
      total_reps: 128,
      total_tonnage_kg: 9280,
    },
    {
      exercise_id: "66666666-6666-4666-8666-666666666666",
      exercise_name: "Conventional Deadlift",
      total_sets: 15,
      total_reps: 75,
      total_tonnage_kg: 13500,
    },
    {
      exercise_id: "77777777-7777-4777-8777-777777777777",
      exercise_name: "Dip",
      total_sets: 14,
      total_reps: 112,
      total_tonnage_kg: null,
    },
    {
      exercise_id: "88888888-8888-4888-8888-888888888888",
      exercise_name: "Romanian Deadlift",
      total_sets: 12,
      total_reps: 96,
      total_tonnage_kg: 8640,
    },
  ],
};

/**
 * Personal records, flattened for display. `PrList` itself needs signed illustration URLs from an
 * authenticated read, which a logged-out marketing route has no way to obtain, so the records
 * panel is rebuilt here from the same tokens rather than faked with placeholder images.
 */
export const demoRecords = [
  { name: "Barbell Bench Press", label: "Heaviest", value: "82.5 kg", when: "2 days ago" },
  { name: "Pull-Up", label: "Most reps", value: "14 reps", when: "last week" },
  { name: "Back Squat", label: "Heaviest", value: "125 kg", when: "last week" },
  { name: "Dead Hang", label: "Longest hold", value: "92s", when: "3 weeks ago" },
] as const;

/** Calisthenics skill-tree progress, the secondary module. */
export const demoSkills = [
  { name: "Handstand", percent: 72, stage: 4, stages: 5, step: "Wall-facing, 45s" },
  { name: "Muscle-Up", percent: 45, stage: 3, stages: 5, step: "Explosive pull-up" },
  { name: "Front Lever", percent: 30, stage: 2, stages: 5, step: "Advanced tuck" },
  { name: "Pistol Squat", percent: 90, stage: 5, stages: 5, step: "Full rep, both sides" },
] as const;
