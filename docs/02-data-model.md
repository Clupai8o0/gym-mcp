# 02 — Data Model (Neon Postgres)

This is the greenfield schema. It is defined in code as **SQLAlchemy 2.0** models and applied
via **Alembic** migrations. The DDL below is the reference target; the models are the source
of truth. Old Supabase data is **not** migrated (archived read-only).

## Conventions

- **PKs:** `uuid` default `gen_random_uuid()` (enable `pgcrypto`).
- **Timestamps:** `timestamptz`, `created_at`/`updated_at` default `now()`; `updated_at`
  maintained by the app (or a trigger).
- **Money/measure units:** weight in **kg** (`numeric`), holds/duration in **seconds**/**int
  minutes** as noted. Display conversions (lb) happen in the UI only.
- **Soft ownership:** every user-owned row has `user_id uuid` FK → `users(id)` `ON DELETE CASCADE`.
- **Enums:** use Postgres `text` + `CHECK` constraints (easy to evolve) rather than native
  enums, matching the current app's style.
- **Naming:** snake_case tables (plural) and columns; index names `<table>_<cols>_idx`.

## Entity map

```
users ──┬──< workout_sessions ──┬──< exercise_sets >── exercises (catalog, global or custom)
        │                       └──< planned_sets >── exercises      # the prescription
        │                              └─ completed_set_id ──> exercise_sets (nullable)
        ├──< personal_records >── exercises
        ├──< skill_progress >── skills (catalog)
        ├──< oauth_clients (dynamic)        # DCR-registered chat clients
        ├──< oauth_authorization_codes
        ├──< oauth_access_tokens
        └──< oauth_refresh_tokens
```

---

## Core domain tables

### `users`
Real accounts. Identity comes from Google OIDC; no passwords stored.

```sql
create table users (
  id           uuid primary key default gen_random_uuid(),
  email        text not null unique,
  google_sub   text not null unique,          -- Google subject id (stable)
  name         text,
  avatar_url   text,
  unit_pref    text not null default 'kg' check (unit_pref in ('kg','lb')),
  created_at   timestamptz not null default now(),
  last_login_at timestamptz
);
```

### `exercises` — the catalog (global + custom)
Global rows have `created_by_user_id = null` and come from the seed. Custom rows are
user-created and scoped by `created_by_user_id`.

```sql
create table exercises (
  id                 uuid primary key default gen_random_uuid(),
  slug               text not null,                 -- stable, url-safe (e.g. 'barbell-bench-press')
  name               text not null,
  category           text,                          -- e.g. strength, stretching, plyometrics, olympic weightlifting
  force              text check (force in ('push','pull','static') or force is null),
  level              text check (level in ('beginner','intermediate','expert') or level is null),
  mechanic           text check (mechanic in ('compound','isolation') or mechanic is null),
  equipment          text,                          -- barbell, dumbbell, body only, machine, ...
  primary_muscles    text[] not null default '{}',
  secondary_muscles  text[] not null default '{}',
  instructions       text[] not null default '{}',  -- ordered how-to steps
  -- provenance & art
  source             text not null default 'free-exercise-db',
  source_id          text,                          -- id/name from the dataset for idempotent upsert
  created_by_user_id uuid references users(id) on delete cascade,   -- null = global catalog
  illustration_url   text,                          -- Vercel Blob URL (null until generated)
  illustration_status text not null default 'pending'
                       check (illustration_status in ('pending','generating','ready','failed')),
  illustration_meta  jsonb,                          -- {model, prompt_hash, size, quality, generated_at}
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

-- global catalog slugs unique; custom exercises unique per user
create unique index exercises_global_slug_uidx on exercises (slug) where created_by_user_id is null;
create unique index exercises_custom_slug_uidx on exercises (created_by_user_id, slug) where created_by_user_id is not null;
create unique index exercises_source_uidx on exercises (source, source_id) where source_id is not null;
create index exercises_category_idx on exercises (category);
create index exercises_primary_muscles_gin on exercises using gin (primary_muscles);
create index exercises_illustration_status_idx on exercises (illustration_status);
-- full-text/trigram search on name (enable pg_trgm)
create index exercises_name_trgm on exercises using gin (name gin_trgm_ops);
```

### `workout_sessions`
Generalized from the old fixed enum: a free `title` plus an optional `type` tag (not enum-locked).

```sql
create table workout_sessions (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references users(id) on delete cascade,
  title            text,                            -- "Upper — Power", free text
  type             text,                            -- optional tag: push/pull/legs/upper/lower/custom...
  performed_at     timestamptz not null,
  ended_at         timestamptz,                     -- null = in progress (Phase 11A, migration 0004)
  notes            text,
  duration_minutes int,                             -- derived from performed_at→ended_at on finish
  created_at       timestamptz not null default now()
);
create index workout_sessions_user_date_idx on workout_sessions (user_id, performed_at desc);
create index workout_sessions_type_idx on workout_sessions (user_id, type);
```

### `exercise_sets`
Now references a catalog `exercise_id` (the key upgrade over the current app).

```sql
create table exercise_sets (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references users(id) on delete cascade,   -- denormalized for fast per-user queries
  session_id    uuid not null references workout_sessions(id) on delete cascade,
  exercise_id   uuid not null references exercises(id),
  set_number    int not null,
  weight_kg     numeric,
  reps          int,
  hold_seconds  int,
  rpe           numeric check (rpe is null or (rpe >= 1 and rpe <= 10)),
  is_pr         boolean not null default false,
  pr_type       text check (pr_type in ('weight','reps','hold_time','first_log') or pr_type is null),
  notes         text,
  created_at    timestamptz not null default now()
);
create index exercise_sets_session_idx on exercise_sets (session_id);
create index exercise_sets_user_exercise_idx on exercise_sets (user_id, exercise_id);
create index exercise_sets_pr_idx on exercise_sets (user_id, exercise_id, is_pr);
```

### `planned_sets`
The **prescription**: what a session is meant to contain, as opposed to what it did (Phase 11N,
migration `0008`). A coach-written plan lives here; nothing in this table is training.

```sql
create table planned_sets (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references users(id) on delete cascade,   -- denormalized, as on exercise_sets
  session_id          uuid not null references workout_sessions(id) on delete cascade,
  exercise_id         uuid not null references exercises(id),
  set_number          int not null,                    -- which set of that movement (1-based)
  order_index         int not null default 0,          -- position in the workout: A1, B1, A2, B2
  target_reps_min     int,                             -- a range; both ends equal = a fixed count
  target_reps_max     int,
  target_weight_kg    numeric,
  target_rpe          numeric check (target_rpe is null or (target_rpe >= 1 and target_rpe <= 10)),
  target_hold_seconds int,
  notes               text,
  completed_set_id    uuid references exercise_sets(id) on delete set null,   -- the set that satisfied it
  deleted_at          timestamptz,                     -- soft delete (docs/02 §Corrections)
  client_key          text,                            -- caller-chosen idempotency key
  created_at          timestamptz not null default now(),
  constraint planned_sets_reps_range_check
    check (target_reps_min is null or target_reps_max is null or target_reps_max >= target_reps_min)
);
create index planned_sets_session_idx on planned_sets (session_id, order_index, set_number);
create index planned_sets_user_exercise_idx on planned_sets (user_id, exercise_id);
create unique index planned_sets_completed_set_uidx on planned_sets (completed_set_id)
  where completed_set_id is not null and deleted_at is null;
create unique index planned_sets_client_key_uidx on planned_sets (user_id, client_key)
  where client_key is not null;
create index planned_sets_deleted_at_idx on planned_sets (deleted_at) where deleted_at is not null;
```

**Why a separate table and not a flag on `exercise_sets`.** Volume, tonnage, frequency and PR
detection all read `exercise_sets` and nothing else. A prescription stored here cannot reach any of
them, so there is no exclusion for six aggregate queries to remember — and no first query to forget
it and credit a lifter with work they were only told to do. It is the stricter sibling of
`is_backfill` (which counts toward volume but not records): a planned row counts toward **neither**,
because it is not a record of anything that happened.

**Completion is read through `completed_set_id`, never from it.** A line is done when the set it
names is still live; a soft-deleted set is not a completion. That is what makes deleting a logged
set reopen its prescribed line with no second write and nothing to re-sync.

The unique index makes one logged set satisfy at most one **live** line, so a session can never
report more completed than logged. Both halves of its predicate matter: without `deleted_at is
null` a *removed* line keeps holding the slot, and the index — not `plans._claimant` — is what
refuses the next completion, turning a domain conflict into a 500. The predicate is deliberately
identical to that function's filter.

That scoping has a consequence `restore` has to handle: while a line is deleted its set is free, so
another line can legally take it. `corrections.restore` therefore clears a restored line's
`completed_set_id` when the set has been claimed in the meantime — it comes back **outstanding**,
which is what is true — rather than putting two live rows in the index and turning the *undo* into a
500.

`on delete set null` (not cascade) means deleting a plan line never deletes the training it
recorded, and `purge_deleted` can free a set's storage without tripping over the plan that named
it. `exercise_id` has **no** `on delete` clause, which is why `exercises.delete_custom` counts
prescribed lines alongside logged sets and refuses (or reassigns) rather than leaving an orphan for
a later purge to hit as a foreign-key violation.

### `personal_records`
One row per (user, exercise, metric). Upserted by the PR-detection logic in `services/sets`.

```sql
create table personal_records (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references users(id) on delete cascade,
  exercise_id   uuid not null references exercises(id),
  pr_type       text not null check (pr_type in ('weight','reps','hold_time')),
  value         numeric not null,
  unit          text not null,                    -- 'kg' | 'reps' | 's'
  achieved_at   timestamptz not null,
  session_id    uuid references workout_sessions(id) on delete set null,
  notes         text,
  constraint personal_records_uidx unique (user_id, exercise_id, pr_type)
);
create index personal_records_user_idx on personal_records (user_id);
```

---

## Skills module (secondary)

Ported from the current app's 13 hardcoded calisthenics skills, now table-driven.

### `skills` — catalog of skill definitions (global)
```sql
create table skills (
  id           uuid primary key default gen_random_uuid(),
  slug         text not null unique,            -- 'planche', 'front_lever', ...
  name         text not null,                   -- 'Planche'
  total_stages int not null,
  stages       jsonb,                           -- optional: [{stage, name, description}]
  related_exercise_id uuid references exercises(id),  -- optional link into the catalog
  created_at   timestamptz not null default now()
);
```
Seed the 13: one_arm_pull_up, human_flag, one_arm_push_up, one_arm_handstand, shrimp_squat,
hefesto, dragon_flag, muscle_up, planche, front_lever, back_lever, handstand_push_up, v_sit
(with the stage counts from the current app — see `lib/tools/skills.ts` in the old repo).

### `skill_progress` — per-user progress
```sql
create table skill_progress (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references users(id) on delete cascade,
  skill_id         uuid not null references skills(id) on delete cascade,
  current_stage    int not null default 0,
  stage_name       text,
  progress_percent int not null default 0 check (progress_percent between 0 and 100),
  notes            text,
  updated_at       timestamptz not null default now(),
  constraint skill_progress_uidx unique (user_id, skill_id)
);
```

---

## OAuth / auth tables

See `05-auth-oauth.md` for how these are used. Tokens are **stored hashed** (SHA-256), never
in plaintext, so a DB leak doesn't expose live credentials.

### `oauth_clients` — DCR-registered chat clients
```sql
create table oauth_clients (
  id                       uuid primary key default gen_random_uuid(),
  client_id                text not null unique,
  client_secret_hash       text,                 -- null for public clients (claude.ai is public)
  client_name              text,
  redirect_uris            text[] not null,
  grant_types              text[] not null default '{authorization_code,refresh_token}',
  token_endpoint_auth_method text not null default 'none',   -- public client
  scope                    text,
  is_dynamic               boolean not null default true,     -- registered via DCR
  created_at               timestamptz not null default now()
);
create index oauth_clients_client_id_idx on oauth_clients (client_id);
```

### `oauth_authorization_codes` — short-lived, single-use, PKCE-bound
```sql
create table oauth_authorization_codes (
  id                   uuid primary key default gen_random_uuid(),
  code_hash            text not null unique,
  client_id            text not null references oauth_clients(client_id) on delete cascade,
  user_id              uuid not null references users(id) on delete cascade,
  redirect_uri         text not null,
  scope                text,
  code_challenge       text not null,           -- PKCE
  code_challenge_method text not null default 'S256' check (code_challenge_method = 'S256'),
  resource             text,                    -- RFC 8707 resource indicator (the MCP url)
  expires_at           timestamptz not null,    -- ~60s TTL
  consumed_at          timestamptz,
  created_at           timestamptz not null default now()
);
```

### `oauth_access_tokens` — opaque, short TTL
```sql
create table oauth_access_tokens (
  id          uuid primary key default gen_random_uuid(),
  token_hash  text not null unique,
  user_id     uuid not null references users(id) on delete cascade,
  client_id   text not null references oauth_clients(client_id) on delete cascade,
  scope       text,
  expires_at  timestamptz not null,             -- e.g. 1h
  revoked_at  timestamptz,
  created_at  timestamptz not null default now()
);
create index oauth_access_tokens_user_idx on oauth_access_tokens (user_id);
```

### `oauth_refresh_tokens` — rotated on every use
```sql
create table oauth_refresh_tokens (
  id            uuid primary key default gen_random_uuid(),
  token_hash    text not null unique,
  user_id       uuid not null references users(id) on delete cascade,
  client_id     text not null references oauth_clients(client_id) on delete cascade,
  scope         text,
  rotated_from  uuid references oauth_refresh_tokens(id),  -- rotation chain
  expires_at    timestamptz not null,
  revoked_at    timestamptz,
  created_at    timestamptz not null default now()
);
```

> **Web sessions** (Google login for the browser) do **not** need a table if implemented as a
> signed, httpOnly cookie carrying a short-lived session token (sliding expiry). If you prefer
> server-side sessions, add a `web_sessions` table with the same hashed-token pattern. Decide
> in Phase 3 and record it in the Decision Log.

---

## Migration strategy (Alembic)

- **One migration per logical change**, checked in, reviewed, never edited after merge.
- **Baseline migration** (`0001_init`) creates extensions (`pgcrypto`, `pg_trgm`) + all core
  + skills tables. **OAuth tables** land in Phase 3's migration, not the baseline, so the
  data-model phase can complete independently.
- **Two connection strings:** Alembic uses the **direct/unpooled** Neon URL (DDL through
  PgBouncer transaction-pooling is unreliable); the app uses the **pooled** URL.
- **Preview branches:** each Vercel preview should target a **Neon branch** so migrations can
  be tested against a throwaway copy. See `09-deployment-vercel.md`.
- **No destructive migrations** without an explicit, reviewed step. Adding columns is safe;
  dropping requires a two-phase (deprecate → remove) plan.

### Acceptance criteria for the data-model phase
- `alembic upgrade head` from an empty Neon DB creates every core + skills table with the
  indexes above; `alembic downgrade base` cleanly reverses it.
- SQLAlchemy models round-trip (insert/select) for every table in a test against a Neon
  branch (or local Postgres) — see `12-conventions.md` for the test harness.
- No table references application logic; this phase is schema only.


## Corrections (Phase 11L)

The write path was only half built: everything could be created, nothing could be taken back.
Migration `0007_corrections` adds the storage for the other half. All of it is additive and
nullable, so it is a metadata-only change and every existing row means what it always meant.

| Column / table | Where | Why |
|---|---|---|
| `deleted_at` | `workout_sessions`, `exercise_sets`, `exercises`, `personal_records_history` | Soft delete. `NULL` = live. Excluded from every read; `restore` clears it. |
| `client_key` | `workout_sessions`, `exercise_sets`, `personal_records_history` | Caller-chosen idempotency key, unique per user. A retry returns the original row. |
| `counted` | `personal_records_history` | Did this entry set a record? Keeps history monotonic — see below. |
| `is_backfill` | `exercise_sets` | Entered after the fact. Counts toward volume; excluded from PR detection. |
| `exercise_slug_aliases` | new table | A slug an exercise used to have, still resolvable after a rename. |

**`personal_records` deliberately has no `deleted_at`.** It is fully derived by the recompute, and
a soft-deleted row would still occupy its `(user_id, exercise_id, pr_type)` unique slot — the next
recalculation would find a row it must neither update nor duplicate. Deleting a record is
expressed as withdrawing the hand-entered claim behind it and recalculating, which is also the
only reading of "I never set that" the log can actually support.

**Why `counted` exists.** `auto` history rows are output: they are written only when a set sets a
record, so they always count. `manual` rows are *input* — the claim has to stay in the table so a
later replay can use it as a floor, but a claim that never beat the running best at its own moment
must not appear in the chronology, or history stops being monotonic. Marking it rather than
rejecting it is what lets it count again later, when the set that outranked it is deleted.

The invariant all of this exists to hold, checked by `services/integrity.verify`: **for every
(exercise, metric), the counted chronology strictly increases and its last value is the standing
record.**

## Planning (Phase 11N)

A session could only ever hold sets that had already happened, so a coach-written plan had nowhere
to live: the only way to say "5×5 at 100 kg on Tuesday" was to log five sets nobody had done — a
lie the moment anything read volume or records. Migration `0008_planned_sets` adds the other half:
what a session is *meant* to contain, beside what it did.

One new table, nothing altered. No column was added to `exercise_sets` and no existing query
changed, which is the point.

| Rule | Where it lives | Why |
|---|---|---|
| A prescription is never training | `planned_sets` is its own table; no aggregate joins it | Volume, tonnage, frequency and PR detection read `exercise_sets` only, so the invariant holds by construction rather than by six queries remembering a filter |
| One door between the two | `services/plans.complete` | It calls `services/sets.log_set` — the same write the log button makes, same PR detection, same `client_key` guard — then records the set's id on the line. A second write path would be a second set of rules |
| Completion is derived, not stored | `completed_set_id` + "is that set still live?" | Deleting the logged set reopens the line with no second write; a soft-deleted set can never read as adherence |
| Off-plan work is never blocked | nothing gates `log_set` | You added a movement, did an extra set, swapped an exercise. `session_progress` reports it as `off_plan_count` rather than refusing it — a tool that blocks training because nobody wrote it down first is worse than no plan |
| A plan cannot outlive its session | `sessions.delete` cascades `planned_sets` unconditionally | `cascade` guards *logged training*, the part you might reasonably keep; there is no "keep the plan, drop the workout" |
| A plan is not a session you trained | `analytics.frequency` skips sessions that hold a prescription (deleted lines included) and no live set | `frequency` counts `workout_sessions` rows, not sets, so it is the one arm of the invariant a separate table does not hold on its own — a plan written for Tuesday would otherwise register as a session trained the moment it was written. Deleted lines count as "was a prescription", or tidying away a plan you never started would *raise* your training count. An *unplanned* empty session still counts: that is what "I started a workout" has always meant here |
| A referenced exercise is never purged | `corrections.purge` skips an exercise that any `exercise_sets` or `planned_sets` row still names | Each table is filtered by its **own** age, so an exercise deleted 90 days ago and a row naming it deleted 5 days ago fall on opposite sides of any cutoff — and neither foreign key carries an `ON DELETE`. Declining is right: it goes on a later run once the rows naming it have aged out. Closes the same pre-existing hole for `exercise_sets` |

**A future-dated session is not in progress.** `plan_session` is the first thing in Tempo that
creates a session dated ahead of now, and the lifecycle only ever looked backwards: both staleness
clauses in `get_active_session` measure a negative age for a future date, so a plan for next Tuesday
satisfied every "still live" test and — ordered newest-first — sorted *above* the workout actually
under way and took its place. `services/sessions.SCHEDULING_SKEW` (5 minutes, for clock skew) is the
line: past it a session is scheduled, neither returned as active nor swept as abandoned, and it
becomes the active session on its own once its start passes. See **D36**.

**Both aggregates now exclude soft-deleted rows.** `analytics.volume` and `analytics.frequency`
never filtered `deleted_at`, so a deleted session's tonnage stayed in every total permanently and
nothing could take it back — `purge_deleted` frees storage, it is not an undo for a number. A
pre-existing bug, fixed here because a deleted *plan-only* session is exactly the case the rule
above is about.

**Adherence is `null`, not `0`, when nothing was prescribed.** `finish_session` reports
`{planned_total, completed_count, pending_count, off_plan_count, percent}`; on a session logged
without a plan, both 0% and 100% would be claims about a prescription that never existed.
