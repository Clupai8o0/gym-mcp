/**
 * Appearance preference — light, dark, or follow the system (the default).
 *
 * **Why a cookie and not `localStorage`.** The server has to read this. Every exercise ships two
 * illustration assets — bold off-white linework for dark surfaces, the same art inverted to
 * near-black for light ones (docs/06) — and the right one has to be in the HTML that the browser
 * first parses, or the art arrives wrong and swaps after hydration. `localStorage` is invisible to
 * the server; a cookie is not. `lib/rail.ts` reaches for one for the same reason.
 *
 * **Colour doesn't wait for the server.** `design/tokens.css` swaps the whole palette off one
 * `color-scheme` declaration keyed to `[data-theme]`, and the bootstrap script below stamps that
 * attribute from this same cookie before the first paint. That keeps the statically prerendered
 * marketing and offline routes — which have no request context to read a cookie from — flash-free
 * as well, and it means a mid-session flip is a single attribute write, not a re-render.
 */
export const THEME_COOKIE = "tempo_theme";

export type ThemePreference = "light" | "dark" | "system";

/** Display order for the segmented control: the two explicit choices, then the default. */
export const THEME_PREFERENCES: readonly ThemePreference[] = ["light", "dark", "system"] as const;

/** One year; this is a UI preference, not session state. */
const MAX_AGE = 60 * 60 * 24 * 365;

/** Narrow an untrusted cookie value, falling back to the default. */
export function toThemePreference(value: string | undefined): ThemePreference {
  return value === "light" || value === "dark" ? value : "system";
}

/** Persist the preference from the browser. */
export function writeThemePreference(preference: ThemePreference): void {
  document.cookie = `${THEME_COOKIE}=${preference}; path=/; max-age=${MAX_AGE}; samesite=lax`;
}

/**
 * Stamp the resolved preference on `<html>`. `system` removes the attribute rather than writing
 * a value, so the `color-scheme: light dark` default on `:root` hands control back to the OS —
 * including live, if the viewer flips their system appearance while the tab is open.
 */
export function applyTheme(preference: ThemePreference): void {
  if (preference === "system") {
    delete document.documentElement.dataset.theme;
  } else {
    document.documentElement.dataset.theme = preference;
  }
}

/**
 * The blocking bootstrap, inlined as the first thing in `<body>` so it runs before the browser
 * paints anything. Deliberately tiny and dependency-free: read the cookie, stamp the attribute,
 * never throw. It is a fixed string, so Phase 10's CSP can admit it by hash without opening up
 * `script-src 'unsafe-inline'`.
 */
export const THEME_BOOTSTRAP = `(function(){try{var m=document.cookie.match(/(?:^|;\\s*)${THEME_COOKIE}=(light|dark)(?=;|$)/);if(m){document.documentElement.dataset.theme=m[1]}}catch(e){}})()`;
