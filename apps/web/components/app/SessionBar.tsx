"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { formatElapsed } from "@/lib/format";
import { useNowSeconds } from "@/lib/hydration";
import styles from "./SessionBar.module.css";

export interface SessionBarProps {
  sessionId: string;
  title: string | null;
  setCount: number;
  /** ISO instant the workout started — the elapsed clock counts up from here. */
  startedAt: string;
}

/**
 * The docked "you are mid-workout" bar (Phase 11B). It sits directly above the tab bar on
 * every screen while a session is live, so browsing the library or checking a PR never means
 * losing the thread back to the set you were about to log.
 *
 * Driven by `get_active_session` (Phase 11A) — `ended_at IS NULL`, never a date. It hides on
 * the session's own page, where it would only repeat the header it is pointing at.
 */
export function SessionBar({ sessionId, title, setCount, startedAt }: SessionBarProps) {
  const pathname = usePathname();
  const nowSeconds = useNowSeconds();
  const elapsed =
    nowSeconds === null ? null : formatElapsed(nowSeconds - new Date(startedAt).getTime() / 1000);

  if (pathname === `/log/${sessionId}`) return null;

  return (
    <Link
      href={`/log/${sessionId}`}
      className={styles.bar}
      aria-label={`Resume ${title ?? "workout"} — ${setCount} set${setCount === 1 ? "" : "s"} logged`}
    >
      <span className={styles.pulse} aria-hidden />
      <span className={styles.main}>
        <span className={styles.title}>{title ?? "Workout"}</span>
        <span className={styles.meta}>
          {setCount} set{setCount === 1 ? "" : "s"}
        </span>
      </span>
      {/* Reserve the clock's width before it mounts so the bar can't jump (it is client-only:
       * elapsed time depends on `Date.now()`, which a server render cannot agree on). */}
      <span className={`${styles.elapsed} tnum`} aria-hidden={elapsed === null}>
        {elapsed ?? " "}
      </span>
      <span className={styles.chevron} aria-hidden>
        →
      </span>
    </Link>
  );
}
