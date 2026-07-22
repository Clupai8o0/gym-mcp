/**
 * Server-side auth boundary (docs/07 §Auth boundary). The `(app)` layout calls
 * {@link requireUser} to gate the authenticated shell: it resolves the session server-side and
 * redirects to Google login via the API's OAuth issuer when absent — app chrome is never
 * rendered for signed-out users.
 */
import { redirect } from "next/navigation";

import { API_URL, getMe } from "./api";
import type { Me } from "./types";

/** Build the API's Google-login URL, returning the user to `returnTo` afterward. */
export function loginUrl(returnTo = "/library"): string {
  const params = new URLSearchParams({ return_to: returnTo });
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
