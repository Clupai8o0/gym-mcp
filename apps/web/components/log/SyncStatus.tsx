import { cn } from "@/lib/cn";
import styles from "./SyncStatus.module.css";

export interface SyncStatusProps {
  online: boolean;
  pending: number;
}

/**
 * A quiet connectivity + queue indicator for the logging surface (docs/07 §offline). Shows nothing
 * when online and fully synced; otherwise surfaces "Offline" and/or the count of queued set writes
 * so the user knows their logging is safe and will sync on reconnect.
 */
export function SyncStatus({ online, pending }: SyncStatusProps) {
  if (online && pending === 0) return null;
  const label = !online
    ? pending > 0
      ? `Offline · ${pending} set${pending === 1 ? "" : "s"} queued`
      : "Offline · logging saved on this device"
    : `Syncing ${pending} set${pending === 1 ? "" : "s"}…`;

  return (
    <span
      className={cn(styles.status, !online && styles.offline)}
      role="status"
      aria-live="polite"
    >
      <span className={styles.dot} aria-hidden />
      {label}
    </span>
  );
}
