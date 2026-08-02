/**
 * Server-side auth boundary (docs/07 §Auth boundary). The `(app)` layout calls
 * {@link requireUser} to gate the authenticated shell: it resolves the session server-side and
 * redirects to Google login via the API's OAuth issuer when absent — app chrome is never
 * rendered for signed-out users.
 */
import { redirect } from "next/navigation";

import { API_URL, getMe } from "./api";
import { BASE_URL } from "./env";
import type { Me } from "./types";

/**
 * Build the API's Google-login URL, returning the user to `returnTo` afterward.
 * The front door is the dashboard (Phase 11C) — signing in lands on your training, not a catalog.
 *
 * `return_to` has to be an **absolute** URL on our own origin. The API's open-redirect guard
 * (`_safe_return_to`, docs/05 Part A) keeps only values equal to — or under — `WEB_ORIGIN`, and
 * quietly substitutes the site root for anything else. A bare path like `/dashboard` fails that
 * test, so sending one silently landed every sign-in back on the marketing page.
 */
export function loginUrl(returnTo = "/dashboard"): string {
  const params = new URLSearchParams({ return_to: new URL(returnTo, BASE_URL).toString() });
  return `${API_URL}/oauth/login/google?${params.toString()}`;
}

/** Resolve the signed-in user or redirect to login. Use in the `(app)` layout/pages. */
export async function requireUser(returnTo?: string): Promise<Me> {
  const me = await getMe();
  if (!me) {
    redirect(loginUrl(returnTo));
  }
  return me;
}
