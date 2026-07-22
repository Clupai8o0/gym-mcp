"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";
import styles from "./DashboardTabs.module.css";

const TABS = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/skills", label: "Skills" },
] as const;

/** Secondary nav between the Dashboard overview and the (secondary) Skills module (docs/07). */
export function DashboardTabs() {
  const pathname = usePathname();
  return (
    <nav className={styles.tabs} aria-label="Dashboard sections">
      {TABS.map((tab) => {
        const active =
          tab.href === "/dashboard" ? pathname === "/dashboard" : pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(styles.tab, active && styles.active)}
            aria-current={active ? "page" : undefined}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
