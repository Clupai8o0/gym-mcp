"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";
import styles from "./AppNav.module.css";

const LINKS = [
  { href: "/library", label: "Library" },
  { href: "/log", label: "Log" },
  { href: "/dashboard", label: "Dashboard" },
] as const;

/** Primary navigation for the authenticated shell; marks the active surface. */
export function AppNav() {
  const pathname = usePathname();
  return (
    <nav className={styles.nav} aria-label="Primary">
      {LINKS.map((link) => {
        const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            className={cn(styles.link, active && styles.active)}
            aria-current={active ? "page" : undefined}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
