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
users ──┬──< workout_sessions ──< exercise_sets >── exercises (catalog, global or custom)
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
  notes            text,
  duration_minutes int,
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
