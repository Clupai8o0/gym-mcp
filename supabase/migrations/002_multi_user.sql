-- Multi-user support: per-user API tokens and user_id scoping on all data tables.

create extension if not exists "pgcrypto";

-- =========================================================================
-- api_tokens — one row per user / access token
-- =========================================================================
create table if not exists public.api_tokens (
  id         uuid primary key default gen_random_uuid(),
  token      text not null unique,
  user_id    text not null,
  name       text,
  is_beta    boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists api_tokens_token_idx   on public.api_tokens (token);
create index if not exists api_tokens_user_id_idx on public.api_tokens (user_id);

-- =========================================================================
-- Add user_id to all data tables
-- =========================================================================
alter table public.workout_sessions
  add column if not exists user_id text not null default '';

alter table public.exercise_sets
  add column if not exists user_id text not null default '';

alter table public.personal_records
  add column if not exists user_id text not null default '';

alter table public.skill_progressions
  add column if not exists user_id text not null default '';

create index if not exists workout_sessions_user_idx  on public.workout_sessions  (user_id);
create index if not exists exercise_sets_user_idx     on public.exercise_sets     (user_id);
create index if not exists personal_records_user_idx  on public.personal_records  (user_id);
create index if not exists skill_progressions_user_idx on public.skill_progressions (user_id);

-- =========================================================================
-- Update unique constraints to be scoped per user
-- =========================================================================
alter table public.personal_records
  drop constraint if exists personal_records_exercise_type_unique;

alter table public.personal_records
  add constraint personal_records_exercise_type_user_unique
  unique (exercise_name, pr_type, user_id);

alter table public.skill_progressions
  drop constraint if exists skill_progressions_skill_name_key;

alter table public.skill_progressions
  add constraint skill_progressions_skill_name_user_unique
  unique (skill_name, user_id);

-- =========================================================================
-- Grant PostgREST access to the new table
-- =========================================================================
grant all on public.api_tokens to postgres, anon, authenticated, service_role;
