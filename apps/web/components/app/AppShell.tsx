"use client";

import { useCallback, useState } from "react";
import { usePathname } from "next/navigation";

import { writeRailPreference } from "@/lib/rail";
import { OfflineIndicator } from "./OfflineIndicator";
import { TabBar } from "./TabBar";
import styles from "./AppShell.module.css";

export interface AppShellProps {
  children: React.ReactNode;
  /** A workout is in progress — the Log tab goes live and the session bar docks. */
  sessionActive: boolean;
  /** Pre-rendered `SessionBar`, or `null`. Passed in so the shell stays free of data concerns. */
  sessionBar: React.ReactNode;
  /** Rail preference read from the cookie server-side, so the first paint is already correct. */
  railCollapsed: boolean;
}

/**
 * The authenticated shell's client half (Phase 11F): it owns the one piece of chrome state the
 * user controls — whether the desktop rail is collapsed — and stamps it on the shell so
 * `--rail-width` cascades to the content column and the docked bar at once. Everything inside
 * `children` is still server-rendered.
 */
export function AppShell({ children, sessionActive, sessionBar, railCollapsed }: AppShellProps) {
  const [collapsed, setCollapsed] = useState(railCollapsed);
  // Home is the one screen that fills the viewport instead of scrolling (Phase 11F). The shell
  // has to know, because it owns the height and padding the page then divides up.
  const fills = usePathname() === "/dashboard";

  const toggleRail = useCallback(() => {
    setCollapsed((previous) => {
      const next = !previous;
      writeRailPreference(next);
      return next;
    });
  }, []);

  return (
    <div
      className={styles.shell}
      data-session={sessionActive ? "true" : undefined}
      data-rail={collapsed ? "collapsed" : "expanded"}
      data-fill={fills ? "true" : undefined}
    >
      <a href="#main" className={styles.skipLink}>
        Skip to content
      </a>

      <TabBar sessionActive={sessionActive} collapsed={collapsed} onToggleRail={toggleRail} />

      <main id="main" tabIndex={-1} className={styles.main}>
        {children}
      </main>

      <div className={styles.dock}>
        <div className={styles.dockChip}>
          <OfflineIndicator />
        </div>
        {sessionBar}
      </div>
    </div>
  );
}
