-- Workout Tracker MCP — initial schema
-- Run this in the Supabase SQL editor.

create extension if not exists "pgcrypto";

-- =========================================================================
-- workout_sessions
-- =========================================================================
create table if not exists public.workout_sessions (
  id uuid primary key default gen_random_uuid(),
  session_type text not null check (session_type in (
    'upper_power',
    'lower_power',
    'skill_rings',
    'upper_hypertrophy',
    'lower_hypertrophy',
    'custom'
  )),
  date timestamptz not null,
  notes text,
  duration_minutes int,
  created_at timestamptz not null default now()
);

create index if not exists workout_sessions_date_idx
  on public.workout_sessions (date desc);

create index if not exists workout_sessions_type_idx
  on public.workout_sessions (session_type);

-- =========================================================================
-- exercise_sets
-- =========================================================================
create table if not exists public.exercise_sets (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.workout_sessions(id) on delete cascade,
  exercise_name text not null,
  set_number int not null,
  weight_kg numeric,
  reps int,
  hold_seconds int,
  rpe numeric check (rpe is null or (rpe >= 1 and rpe <= 10)),
  is_pr boolean not null default false,
  pr_type text check (pr_type in ('weight', 'reps', 'hold_time', 'first_log')),
  notes text,
  created_at timestamptz not null default now()
);

create index if not exists exercise_sets_session_idx
  on public.exercise_sets (session_id);

create index if not exists exercise_sets_exercise_idx
  on public.exercise_sets (exercise_name);

create index if not exists exercise_sets_pr_idx
  on public.exercise_sets (exercise_name, is_pr);

-- =========================================================================
-- personal_records
-- =========================================================================
create table if not exists public.personal_records (
  id uuid primary key default gen_random_uuid(),
  exercise_name text not null,
  pr_type text not null check (pr_type in ('weight', 'reps', 'hold_time')),
  value numeric not null,
  achieved_at timestamptz not null,
  session_id uuid references public.workout_sessions(id) on delete set null,
  notes text,
  constraint personal_records_exercise_type_unique unique (exercise_name, pr_type)
);

create index if not exists personal_records_exercise_idx
  on public.personal_records (exercise_name);

-- =========================================================================
-- skill_progressions
-- =========================================================================
create table if not exists public.skill_progressions (
  id uuid primary key default gen_random_uuid(),
  skill_name text not null unique,
  current_stage int not null,
  stage_name text not null,
  progress_percent int not null check (progress_percent >= 0 and progress_percent <= 100),
  last_updated timestamptz not null default now(),
  notes text
);
