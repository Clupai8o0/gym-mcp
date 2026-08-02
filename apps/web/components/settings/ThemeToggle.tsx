"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { cn } from "@/lib/cn";
import {
  applyTheme,
  THEME_PREFERENCES,
  writeThemePreference,
  type ThemePreference,
} from "@/lib/theme";
import styles from "./ThemeToggle.module.css";

/** Minimal monochrome glyphs on the same 24px grid as the tab icons (docs/08). Decorative — each
 * option carries a visible text label, so the icon never has to carry the accessible name. */
const GLYPH = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
} as const;

const OPTIONS: Record<ThemePreference, { label: string; icon: React.ReactElement }> = {
  light: {
    label: "Light",
    icon: (
      <svg {...GLYPH} className={styles.icon}>
        <circle cx="12" cy="12" r="4" />
        {/* All eight rays span the same 7.25→9.25 ring, so the starburst stays radially even. */}
        <path d="M12 2.75v2M12 19.25v2M2.75 12h2M19.25 12h2M5.46 5.46l1.41 1.41M17.13 17.13l1.41 1.41M5.46 18.54l1.41-1.41M17.13 6.87l1.41-1.41" />
      </svg>
    ),
  },
  dark: {
    label: "Dark",
    icon: (
      <svg {...GLYPH} className={styles.icon}>
        <path d="M20.25 14.4A8.5 8.5 0 0 1 9.6 3.75a8.5 8.5 0 1 0 10.65 10.65z" />
      </svg>
    ),
  },
  system: {
    label: "System",
    icon: (
      <svg {...GLYPH} className={styles.icon}>
        <rect x="3" y="4.75" width="18" height="12" rx="2" />
        <path d="M9 20.25h6M12 16.75v3.5" />
      </svg>
    ),
  },
};

/**
 * Appearance — light / dark / follow the system (Settings → Preferences). Mirrors
 * {@link UnitToggle}'s segmented control; the difference is where the choice lands.
 *
 * The palette flips synchronously: {@link applyTheme} re-points `color-scheme` on `<html>` and
 * every `light-dark()` token in `design/tokens.css` resolves against it, so there is no round-trip
 * and nothing to re-render. The `router.refresh()` afterwards is for the *illustrations* — those
 * are two distinct assets picked server-side from the cookie, so the server has to speak again
 * before the catalog art matches the new surface (see `IllustrationImage`).
 */
export function ThemeToggle({ current }: { current: ThemePreference }) {
  const router = useRouter();
  const [theme, setTheme] = useState<ThemePreference>(current);

  const choose = (next: ThemePreference) => {
    if (next === theme) return;
    setTheme(next);
    applyTheme(next);
    writeThemePreference(next);
    router.refresh();
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.group} role="group" aria-label="Appearance">
        {THEME_PREFERENCES.map((value) => (
          <button
            key={value}
            type="button"
            className={cn(styles.option, value === theme && styles.active)}
            aria-pressed={value === theme}
            onClick={() => choose(value)}
          >
            {OPTIONS[value].icon}
            {OPTIONS[value].label}
          </button>
        ))}
      </div>
    </div>
  );
}
