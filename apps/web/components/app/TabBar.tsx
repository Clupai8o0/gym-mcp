"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";
import { Logo } from "./Logo";
import { HomeIcon, LibraryIcon, LogIcon, YouIcon, type TabIcon } from "./TabIcons";
import styles from "./TabBar.module.css";

interface Tab {
  href: string;
  label: string;
  Icon: TabIcon;
  /** Extra path prefixes that should still light this tab up. */
  owns?: readonly string[];
}

const TABS: readonly Tab[] = [
  // Home owns the `/progress/*` screens too — they are the sections it summarises (Phase 11C).
  { href: "/dashboard", label: "Home", Icon: HomeIcon, owns: ["/progress"] },
  { href: "/library", label: "Library", Icon: LibraryIcon },
  { href: "/log", label: "Log", Icon: LogIcon },
  { href: "/settings", label: "You", Icon: YouIcon },
];

function isActive(pathname: string, tab: Tab): boolean {
  const roots = [tab.href, ...(tab.owns ?? [])];
  return roots.some((root) => pathname === root || pathname.startsWith(`${root}/`));
}

/** Chevrons pointing at the edge the rail will move toward. */
function CollapseIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn(styles.collapseGlyph, collapsed && styles.collapseGlyphFlipped)}
      aria-hidden
    >
      <path d="M13.5 8.5 10 12l3.5 3.5" />
      <path d="M18 8.5 14.5 12l3.5 3.5" />
    </svg>
  );
}

export interface TabBarProps {
  /** A workout is in progress — Log stops being a destination and becomes a live state. */
  sessionActive: boolean;
  /** Desktop rail is icon-only. Ignored below 768px, where the tab bar is always labelled. */
  collapsed: boolean;
  onToggleRail: () => void;
}

/**
 * The app's primary navigation (Phase 11B). Below 768px it is a bottom tab bar sitting inside
 * the thumb arc; at 768px and up the *same* component becomes a left rail — one set of links,
 * two compositions, so the two can't drift.
 *
 * Icons always ship with labels on mobile: this app is used mid-set, glanced at, and four
 * unlabelled glyphs would be a memory test. The desktop rail can be collapsed to icons on
 * request (Phase 11F) — it defaults to labelled, and the labels stay in the accessibility tree.
 * `Log` takes the accent and a dot badge while a session is live, which is the one piece of
 * state worth carrying in the chrome itself.
 */
export function TabBar({ sessionActive, collapsed, onToggleRail }: TabBarProps) {
  const pathname = usePathname();

  return (
    <nav className={cn(styles.bar, collapsed && styles.collapsedRail)} aria-label="Primary">
      <div className={styles.railHead}>
        <Link href="/dashboard" className={styles.brand} aria-label="Tempo home">
          <Logo className={styles.brandMark} />
          <span className={styles.brandName}>Tempo</span>
        </Link>
        <button
          type="button"
          className={styles.collapse}
          onClick={onToggleRail}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          title={collapsed ? "Expand navigation" : "Collapse navigation"}
        >
          <CollapseIcon collapsed={collapsed} />
        </button>
      </div>

      <ul className={styles.tabs}>
        {TABS.map((tab) => {
          const active = isActive(pathname, tab);
          const live = tab.href === "/log" && sessionActive;
          return (
            <li key={tab.href} className={styles.item}>
              <Link
                href={tab.href}
                className={cn(styles.tab, active && styles.active, live && styles.live)}
                aria-current={active ? "page" : undefined}
                title={collapsed ? tab.label : undefined}
              >
                <span className={styles.indicator} aria-hidden />
                <span className={styles.iconWrap}>
                  <tab.Icon className={styles.icon} />
                  {live && <span className={styles.badge} aria-hidden />}
                </span>
                <span className={styles.label}>{tab.label}</span>
                {live && <span className="sr-only">workout in progress</span>}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
