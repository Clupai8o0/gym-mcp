/**
 * Client-safe environment constants. Kept separate from `lib/api.ts` (which imports the
 * server-only `next/headers`) so client components can read the API origin without pulling
 * server code into the browser bundle. `NEXT_PUBLIC_*` is inlined at build and safe to expose.
 */
// `||`, not `??`: an env var set to the empty string is a real deployment mistake, and `??`
// would keep it — yielding an API origin of "" and a browser that calls its own origin for
// every mutation. Empty is never a URL anyone meant.
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

/**
 * This app's own origin. Must match the API's `WEB_ORIGIN` exactly — the login endpoint checks
 * `return_to` against it and silently falls back to the site root when it doesn't match.
 */
export const BASE_URL =
  process.env.NEXT_PUBLIC_BASE_URL?.replace(/\/$/, "") || "http://localhost:3000";

/** Custom header that forces a CORS preflight — the CSRF signal for cookie-authed writes. */
export const CLIENT_HEADER = "X-Tempo-Client";
