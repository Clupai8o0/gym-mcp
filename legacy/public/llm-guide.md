# Workout Tracker MCP — LLM Guide

## What this server does

This MCP server lets you log and query gym workouts for a single user. It tracks:
- **Workout sessions** (type, date, duration, notes)
- **Exercise sets** within each session (reps, weight, hold time, RPE)
- **Personal records** (auto-detected on log_set, or manually logged)
- **Calisthenics skill progressions** (13 skills with stage-based tracking)

All data is scoped to the authenticated user — you cannot read or write another user's data.

---

## Data model

### Sessions
A session groups all sets done in one training block.

| Field | Type | Notes |
|---|---|---|
| id | uuid | auto-generated |
| session_type | enum | see valid values below |
| date | ISO 8601 | e.g. \`2025-01-15T10:00:00Z\` |
| duration_minutes | int | optional |
| notes | text | optional |

**Valid session_type values:**
\`upper_power\`, \`lower_power\`, \`skill_rings\`, \`upper_hypertrophy\`, \`lower_hypertrophy\`, \`custom\`

### Exercise sets
One row per set. Belongs to a session.

| Field | Type | Notes |
|---|---|---|
| session_id | uuid | must exist |
| exercise_name | text | free-form, e.g. \`bench_press\` |
| set_number | int | 1-based |
| weight_kg | numeric | null for bodyweight |
| reps | int | null for holds/timed |
| hold_seconds | int | null for rep-based |
| rpe | numeric 1–10 | optional |
| is_pr | bool | set automatically |
| pr_type | enum | weight / reps / hold_time / first_log |

### Personal records
One row per (exercise_name, pr_type) pair — upserted automatically when a PR is detected.

**Valid pr_type values for manual logging:** \`weight\`, \`reps\`, \`hold_time\`

### Skill progressions
One row per skill. Upserted on each update.

**The 13 tracked skills and their stage counts:**
| Skill | Stages |
|---|---|
| back_lever | 5 |
| dragon_flag | 7 |
| front_lever | 6 |
| handstand_push_up | 5 |
| hefesto | 6 |
| human_flag | 8 |
| muscle_up | 5 |
| one_arm_handstand | 11 |
| one_arm_pull_up | 6 |
| one_arm_push_up | 8 |
| planche | 6 |
| shrimp_squat | 5 |
| v_sit | 8 |

---

## Tools reference

### Sessions

#### log_session
Create a new workout session. Call this first before logging any sets.

**Input:**
- \`session_type\` (required) — one of the valid enum values
- \`date\` (required) — ISO 8601 string
- \`duration_minutes\` (optional) — integer
- \`notes\` (optional) — free text

**Returns:** \`{ session_id, session_type, date }\`

---

#### get_session
Fetch a session and all its sets grouped by exercise name.

**Input:** \`session_id\` (uuid)

**Returns:** \`{ session, sets_by_exercise }\`
- \`sets_by_exercise\` is an object keyed by exercise name, each value is an array of set rows.

---

#### list_sessions
Paginated list of sessions, newest first.

**Input (all optional):**
- \`session_type\` — filter by type
- \`from_date\`, \`to_date\` — ISO 8601 date range
- \`limit\` (default 20, max 100), \`offset\` (default 0)

**Returns:** \`{ sessions, total, limit, offset }\`

---

### Sets

#### log_set
Log one set within a session. Automatically checks for PRs and updates \`personal_records\` if a new best is detected.

**Input:**
- \`session_id\` (required) — must be an existing session
- \`exercise_name\` (required) — free-form string
- \`set_number\` (required) — integer, 1-based
- \`weight_kg\` (optional) — omit for bodyweight exercises
- \`reps\` (optional)
- \`hold_seconds\` (optional) — for static holds
- \`rpe\` (optional) — 1–10
- \`notes\` (optional)

Provide at least one of \`reps\`, \`weight_kg\`, or \`hold_seconds\`.

**Returns:** \`{ set_id, is_pr, pr_type, previous_best }\`
- \`is_pr: true\` means a new personal record was detected and saved.

---

#### get_session_sets
Return all sets for a session grouped by exercise name.

**Input:** \`session_id\` (uuid)

**Returns:** \`{ sets_by_exercise }\`

---

### Personal records

#### get_prs
Return all personal records, optionally filtered to one exercise.

**Input (optional):** \`exercise_name\`

**Returns:** \`{ prs }\` — array of \`{ exercise_name, pr_type, value, achieved_at }\`

---

#### get_pr_history
Chronological list of every set that was a PR for a given exercise and type.

**Input:**
- \`exercise_name\` (required)
- \`pr_type\` (required) — \`weight\`, \`reps\`, or \`hold_time\`

**Returns:** \`{ history }\` — array of set rows with joined session info

---

#### log_pr
Manually upsert a personal record. Use this for skill holds, one-off bests logged outside a session, or to correct a record.

**Input:**
- \`exercise_name\` (required)
- \`pr_type\` (required) — \`weight\`, \`reps\`, or \`hold_time\`
- \`value\` (required) — numeric
- \`achieved_at\` (required) — ISO 8601 date
- \`session_id\` (optional) — link to an existing session
- \`notes\` (optional)

**Returns:** \`{ pr }\`

---

### Skills

#### update_skill_progress
Upsert progress for a skill. Creates the row if it doesn't exist.

**Input:**
- \`skill_name\` (required) — must be one of the 13 tracked skills
- \`current_stage\` (required) — integer, 0-based
- \`stage_name\` (required) — human-readable name for this stage
- \`progress_percent\` (required) — 0–100
- \`notes\` (optional)

**Returns:** \`{ skill }\`

---

#### get_skill_overview
Return all 13 skills at once. Skills with no stored progress appear as stage 0 / 0%.

**Input:** none

**Returns:** \`{ skills }\` — array of 13 skill rows, sorted alphabetically

---

#### get_skill_detail
Return progress for one skill plus its total stage count.

**Input:** \`skill_name\`

**Returns:** \`{ skill, total_stages }\`

---

### Analytics

#### get_volume_summary
Total sets, reps, and tonnage (kg × reps) grouped by exercise, for a date range.

**Input:**
- \`from_date\` (required) — ISO 8601
- \`to_date\` (required) — ISO 8601
- \`exercise_name\` (optional) — filter to a single exercise

**Returns:** \`{ from_date, to_date, summary }\`
- Each bucket: \`{ exercise_name, total_sets, total_reps, total_tonnage_kg }\`
- \`total_tonnage_kg\` is \`null\` if any set in the bucket had no weight (bodyweight).

---

#### get_session_frequency
Sessions per ISO week for the last N weeks, useful for consistency tracking.

**Input (optional):** \`weeks\` (default 8, max 104)

**Returns:** \`{ weeks, frequency }\`
- Each entry: \`{ week_start, count }\` where \`week_start\` is the Monday of that ISO week.

---

## Common workflows

### Log a full session
1. \`log_session\` — get back a \`session_id\`
2. For each set: \`log_set\` with the \`session_id\`
3. Optionally call \`get_session\` at the end to confirm everything was saved

### Review last session
1. \`list_sessions\` with \`limit: 1\` — get the most recent \`session_id\`
2. \`get_session\` — see all sets

### Check progress on an exercise
1. \`get_prs\` with \`exercise_name\` — see current bests
2. \`get_pr_history\` — see how the PRs progressed over time

### Weekly training analysis
1. \`get_session_frequency\` — check consistency
2. \`get_volume_summary\` with a date range — see volume by exercise

### Update a skill level
1. \`get_skill_detail\` to see current stage
2. \`update_skill_progress\` with new stage info

---

## Tips

- **Always create a session first.** \`log_set\` requires a valid \`session_id\`.
- **set_number is 1-based per exercise.** If logging 3 sets of bench press, use \`set_number\` 1, 2, 3.
- **exercise_name is free-form** but should be consistent across sessions for PR detection and analytics to work (e.g. always use \`bench_press\` not sometimes \`Bench Press\`).
- **PR detection is automatic** on \`log_set\`. Only call \`log_pr\` for manual corrections or skill holds logged outside a session.
- **Dates must be ISO 8601.** Use \`YYYY-MM-DDTHH:mm:ssZ\` or just \`YYYY-MM-DD\` for date-only values.
- **Bodyweight sets**: omit \`weight_kg\` entirely. Tonnage will be \`null\` for any exercise that has bodyweight sets.
