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
  { href: "/dashboard", label: "Home", Icon: HomeIcon },
  { href: "/library", label: "Library", Icon: LibraryIcon },
  { href: "/log", label: "Log", Icon: LogIcon },
  { href: "/settings", label: "You", Icon: YouIcon },
];

function isActive(pathname: string, tab: Tab): boolean {
  const roots = [tab.href, ...(tab.owns ?? [])];
  return roots.some((root) => pathname === root || pathname.startsWith(`${root}/`));
}

export interface TabBarProps {
  /** A workout is in progress — Log stops being a destination and becomes a live state. */
  sessionActive: boolean;
}

/**
 * The app's primary navigation (Phase 11B). Below 768px it is a bottom tab bar sitting inside
 * the thumb arc; at 768px and up the *same* component becomes a left rail — one set of links,
 * two compositions, so the two can't drift.
 *
 * Icons always ship with labels: this app is used mid-set, glanced at, and four unlabelled
 * glyphs would be a memory test. `Log` takes the accent and a dot badge while a session is
 * live, which is the one piece of state worth carrying in the chrome itself.
 */
export function TabBar({ sessionActive }: TabBarProps) {
  const pathname = usePathname();

  return (
    <nav className={styles.bar} aria-label="Primary">
      <Link href="/dashboard" className={styles.brand} aria-label="Tempo home">
        <Logo className={styles.brandMark} />
        <span className={styles.brandName}>Tempo</span>
      </Link>

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
              >
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
