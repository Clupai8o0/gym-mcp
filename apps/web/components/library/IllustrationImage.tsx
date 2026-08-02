/**
 * Server-component entry point for the exercise illustration.
 *
 * Every exercise ships two assets, one per surface — bold off-white linework for dark, the same
 * art inverted to near-black for light (docs/06) — and the choice is made from the theme cookie so
 * the right one is in the HTML the browser first parses. That cookie read is *all* this file adds:
 * the rendering lives in {@link IllustrationView}, which is synchronous and importable from client
 * code too (the Library grid needs it there to render the pages it appends on scroll).
 *
 * The preference is read here rather than threaded through every caller — the callers that use
 * this wrapper (the detail page, the dashboard's `PrList`) are server components on already-dynamic
 * routes, so the cookie read costs nothing they weren't paying.
 */
import { cookies } from "next/headers";

import { THEME_COOKIE, toThemePreference } from "@/lib/theme";
import type { IllustrationStatus } from "@/lib/types";
import { IllustrationView, type IllustrationViewProps } from "./IllustrationView";

export type IllustrationImageProps = Omit<IllustrationViewProps, "preference">;

/** {@link IllustrationView}, with the viewer's appearance preference resolved from the cookie. */
export async function IllustrationImage(props: IllustrationImageProps) {
  const preference = toThemePreference((await cookies()).get(THEME_COOKIE)?.value);
  return <IllustrationView {...props} preference={preference} />;
}

// Deliberately not re-exporting `IllustrationView`: this module imports `next/headers`, so any
// client component reaching for the view through here would drag server-only code into the
// browser bundle. Client callers import `./IllustrationView` directly.
export type { IllustrationStatus };
