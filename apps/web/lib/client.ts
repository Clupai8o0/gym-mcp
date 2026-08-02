/**
 * Browser-side API client for mutations + interactive reads (docs/07 §Data fetching). Unlike the
 * server client (`lib/api.ts`, which forwards the session cookie), these run in the browser: they
 * hit the public API origin with `credentials:'include'` (sends the parent-domain session cookie)
 * and the `X-Tempo-Client` header, which forces a CORS preflight — the CSRF signal for
 * cookie-authenticated writes (docs/05). Fully typed off the generated OpenAPI schema; no `any`.
 *
 * Safe to import from client components only — it never pulls in server-only modules.
 */
import { API_URL, CLIENT_HEADER } from "./env";
import type {
  ExerciseDetail,
  ExerciseList,
  LoggedSet,
  Me,
  MeUpdate,
  RevokeConnection,
  Session,
  SetCreate,
  SetUpdate,
  SkillProgress,
  SkillProgressUpdate,
} from "./types";

export class ClientApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ClientApiError";
  }
}

/** True for a network failure (offline / API unreachable) — the caller may queue the write. */
export class NetworkError extends Error {
  constructor(cause?: unknown) {
    super("Network request failed");
    this.name = "NetworkError";
    this.cause = cause;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal } = options;
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      signal,
      credentials: "include",
      headers: {
        [CLIENT_HEADER]: "web",
        ...(body !== undefined ? { "content-type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (cause) {
    // A caller-cancelled request (AbortController) is not a network failure — rethrow as-is.
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    // fetch otherwise only rejects on network-layer failure (offline, DNS, CORS) — never on status.
    throw new NetworkError(cause);
  }
  if (response.status === 204) return undefined as T;
  if (!response.ok) {
    let message = `${method} ${path} → ${response.status}`;
    try {
      const payload = (await response.json()) as { error?: { message?: string } };
      if (payload.error?.message) message = payload.error.message;
    } catch {
      // Non-JSON error body — keep the status-line message.
    }
    throw new ClientApiError(response.status, message);
  }
  return (await response.json()) as T;
}

// ── Exercises (interactive search + the Library's scroll pagination) ────────────────────────

/** The catalog filters the Library reflects in the URL, plus a window into the result set. */
export interface ExerciseQuery {
  q?: string;
  muscle?: string;
  equipment?: string;
  category?: string;
  level?: string;
  limit?: number;
  offset?: number;
}

/**
 * One page of the catalog, fetched **from the browser**.
 *
 * The server twin of this (`lib/api.ts`) goes through the Next.js function; this one talks to the
 * API directly, so a scroll-triggered page is a single hop instead of browser → Next → API.
 */
export async function listExercises(
  query: ExerciseQuery = {},
  signal?: AbortSignal,
): Promise<ExerciseList> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return request<ExerciseList>(`/api/exercises${qs ? `?${qs}` : ""}`, { signal });
}

export async function searchExercises(query: string, signal?: AbortSignal): Promise<ExerciseList> {
  return listExercises({ q: query.trim() || undefined, limit: 20 }, signal);
}

export async function getExerciseBySlug(slug: string): Promise<ExerciseDetail> {
  return request<ExerciseDetail>(`/api/exercises/by-slug/${encodeURIComponent(slug)}`);
}

// ── Sessions ───────────────────────────────────────────────────────────────────────────────
export async function createSession(payload: {
  performed_at: string;
  title?: string | null;
  type?: string | null;
}): Promise<Session> {
  return request<Session>("/api/sessions", { method: "POST", body: payload });
}

export async function updateSession(
  sessionId: string,
  changes: { title?: string | null; type?: string | null; duration_minutes?: number | null },
): Promise<Session> {
  return request<Session>(`/api/sessions/${sessionId}`, { method: "PATCH", body: changes });
}

export async function deleteSession(sessionId: string): Promise<void> {
  await request<void>(`/api/sessions/${sessionId}`, { method: "DELETE" });
}

/** End a workout and store its duration (Phase 11A). Idempotent server-side — safe to retry. */
export async function finishSession(sessionId: string): Promise<Session> {
  return request<Session>(`/api/sessions/${sessionId}/finish`, { method: "POST" });
}

// ── Sets ───────────────────────────────────────────────────────────────────────────────────
export async function logSet(sessionId: string, payload: SetCreate): Promise<LoggedSet> {
  return request<LoggedSet>(`/api/sessions/${sessionId}/sets`, { method: "POST", body: payload });
}

export async function updateSet(setId: string, changes: SetUpdate): Promise<LoggedSet> {
  return request<LoggedSet>(`/api/sets/${setId}`, { method: "PATCH", body: changes });
}

export async function deleteSet(setId: string): Promise<void> {
  await request<void>(`/api/sets/${setId}`, { method: "DELETE" });
}

// ── Skills (edit progress) ───────────────────────────────────────────────────────────────────
export async function updateSkillProgress(
  slug: string,
  payload: SkillProgressUpdate,
): Promise<SkillProgress> {
  return request<SkillProgress>(`/api/skills/${encodeURIComponent(slug)}/progress`, {
    method: "PUT",
    body: payload,
  });
}

// ── Settings ─────────────────────────────────────────────────────────────────────────────────
export async function updatePreferences(payload: MeUpdate): Promise<Me> {
  return request<Me>("/api/me", { method: "PATCH", body: payload });
}

export async function revokeConnection(clientId: string): Promise<RevokeConnection> {
  return request<RevokeConnection>(`/api/connections/${encodeURIComponent(clientId)}`, {
    method: "DELETE",
  });
}
