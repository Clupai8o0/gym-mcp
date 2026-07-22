/**
 * Server-side typed API client. Server Components call the FastAPI backend directly and forward
 * the incoming `tempo_session` cookie so the initial render is authenticated and fast (docs/07
 * §Data fetching). All reads go through here; responses are typed from the generated OpenAPI
 * schema (`lib/types`), never `any`.
 *
 * Browser mutations (added in later phases) will call the same host with `credentials:'include'`
 * + the `X-Tempo-Client` CSRF header; we send that header here too for parity.
 */
import { cache } from "react";
import { cookies } from "next/headers";

import { API_URL, CLIENT_HEADER } from "./env";
import type {
  ConnectionList,
  Exercise,
  ExerciseDetail,
  ExerciseList,
  Frequency,
  Me,
  PrList,
  SessionDetail,
  SessionList,
  SkillsOverview,
  Volume,
} from "./types";

export { API_URL };

/**
 * Base for server-side (RSC) fetches. In production this can be an internal API origin
 * (`API_INTERNAL_URL`) to skip a public round-trip; it falls back to the public API URL. Only
 * read server-side, so it may reference a non-public host safely.
 */
const SERVER_API_URL = process.env.API_INTERNAL_URL?.replace(/\/$/, "") ?? API_URL;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Low-level authenticated fetch: forwards the session cookie, throws {@link ApiError} on !ok. */
async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const cookieHeader = (await cookies()).toString();
  const response = await fetch(`${SERVER_API_URL}${path}`, {
    ...init,
    headers: {
      ...init?.headers,
      [CLIENT_HEADER]: "web",
      ...(cookieHeader ? { cookie: cookieHeader } : {}),
    },
    // User data is per-request; never share a cache across users.
    cache: "no-store",
  });
  return response;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  if (!response.ok) {
    throw new ApiError(response.status, `GET ${path} → ${response.status}`);
  }
  return (await response.json()) as T;
}

/** The signed-in user, or `null` if the session is absent/expired (401) or the API is down. */
export const getMe = cache(async (): Promise<Me | null> => {
  try {
    const response = await apiFetch("/api/me");
    if (response.status === 401) return null;
    if (!response.ok) throw new ApiError(response.status, `GET /api/me → ${response.status}`);
    return (await response.json()) as Me;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    // Network failure (e.g. API unreachable in dev) → treat as signed-out rather than crash.
    return null;
  }
});

export interface ExerciseFilters {
  q?: string;
  muscle?: string;
  equipment?: string;
  category?: string;
  level?: string;
  limit?: number;
  offset?: number;
}

export async function listExercises(filters: ExerciseFilters = {}): Promise<ExerciseList> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "" && value !== null) {
      params.set(key, String(value));
    }
  }
  const query = params.toString();
  return getJson<ExerciseList>(`/api/exercises${query ? `?${query}` : ""}`);
}

/** Resolve a Library slug to its full detail (calls the additive `by-slug` endpoint). */
export async function getExerciseBySlug(slug: string): Promise<ExerciseDetail | null> {
  const response = await apiFetch(`/api/exercises/by-slug/${encodeURIComponent(slug)}`);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new ApiError(response.status, `GET by-slug → ${response.status}`);
  }
  return (await response.json()) as ExerciseDetail;
}

/** The user's personal records for one exercise (empty list if none). */
export async function listPrsForExercise(exerciseId: string): Promise<PrList> {
  return getJson<PrList>(`/api/prs?exercise_id=${encodeURIComponent(exerciseId)}`);
}

/** All of the user's personal records, with the exercise art (docs/07 §Dashboard). */
export async function listPrs(): Promise<PrList> {
  return getJson<PrList>("/api/prs");
}

/** Training volume (sets/reps/tonnage per exercise) between two instants — for the Dashboard. */
export async function getVolume(fromIso: string, toIso: string): Promise<Volume> {
  const params = new URLSearchParams({ from: fromIso, to: toIso });
  return getJson<Volume>(`/api/analytics/volume?${params.toString()}`);
}

/** Session counts per ISO week for the last `weeks` weeks (frequency heatmap). */
export async function getFrequency(weeks: number): Promise<Frequency> {
  return getJson<Frequency>(`/api/analytics/frequency?weeks=${weeks}`);
}

/** Every skill with the user's progress (stage 0 / 0% when not started). */
export async function getSkillsOverview(): Promise<SkillsOverview> {
  return getJson<SkillsOverview>("/api/skills");
}

/** The user's active OAuth grants (Settings → Connected apps). */
export async function listConnections(): Promise<ConnectionList> {
  return getJson<ConnectionList>("/api/connections");
}

/** Recent workout sessions, newest first (docs/07 §Log — the `/log` home list). */
export async function listSessions(limit = 20, offset = 0): Promise<SessionList> {
  return getJson<SessionList>(`/api/sessions?limit=${limit}&offset=${offset}`);
}

/** One session with its sets grouped by exercise, or `null` if not found / not the user's. */
export async function getSession(sessionId: string): Promise<SessionDetail | null> {
  const response = await apiFetch(`/api/sessions/${encodeURIComponent(sessionId)}`);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new ApiError(response.status, `GET session → ${response.status}`);
  }
  return (await response.json()) as SessionDetail;
}

export type { Exercise };
