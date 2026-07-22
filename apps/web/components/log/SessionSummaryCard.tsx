import Link from "next/link";

import { Badge, Card } from "@/components/ui";
import { formatDuration, formatRelativeDate, titleCase } from "@/lib/format";
import type { Session } from "@/lib/types";
import styles from "./SessionSummaryCard.module.css";

/**
 * A recent-workout row on the `/log` home (docs/07 §Log). Links to that session's logging surface.
 * Server-rendered — no interactivity beyond the link.
 */
export function SessionSummaryCard({ session }: { session: Session }) {
  return (
    <Link href={`/log/${session.id}`} className={styles.link} prefetch={false}>
      <Card interactive className={styles.card}>
        <div className={styles.main}>
          <p className={styles.name}>{session.title ?? "Workout"}</p>
          <p className={styles.date}>{formatRelativeDate(session.performed_at)}</p>
        </div>
        <div className={styles.meta}>
          {session.type && <Badge>{titleCase(session.type)}</Badge>}
          {session.duration_minutes != null && (
            <span className={styles.duration}>{formatDuration(session.duration_minutes)}</span>
          )}
          <span className={styles.chevron} aria-hidden>
            →
          </span>
        </div>
      </Card>
    </Link>
  );
}
