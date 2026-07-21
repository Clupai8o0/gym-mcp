import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/**
 * Shared flat ESLint config for Next.js apps in the Tempo monorepo.
 *
 * Wraps `eslint-config-next` (core-web-vitals + typescript) so every web surface
 * lints identically. Apps compose this and add only app-specific ignores.
 */
export default [...nextVitals, ...nextTs];
