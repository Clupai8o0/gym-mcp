/**
 * Desktop rail collapse state.
 *
 * Persisted in a plain cookie rather than `localStorage` so the **server** can stamp it onto the
 * shell during SSR. Reading it on the client after mount would collapse the rail one frame late
 * on every navigation, and the usual fix — an inline bootstrap script in `<head>` — buys a
 * `script-src 'unsafe-inline'` obligation that Phase 10's CSP would then have to carry.
 */
export const RAIL_COOKIE = "tempo_rail";
export const RAIL_COLLAPSED = "collapsed";
export const RAIL_EXPANDED = "expanded";

/** One year; this is a UI preference, not session state. */
const MAX_AGE = 60 * 60 * 24 * 365;

/** Persist the preference from the browser. */
export function writeRailPreference(collapsed: boolean): void {
  const value = collapsed ? RAIL_COLLAPSED : RAIL_EXPANDED;
  document.cookie = `${RAIL_COOKIE}=${value}; path=/; max-age=${MAX_AGE}; samesite=lax`;
}
