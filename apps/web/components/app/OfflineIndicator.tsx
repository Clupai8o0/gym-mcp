"use client";

import { useOnline } from "@/lib/offline/useOnline";
import styles from "./OfflineIndicator.module.css";

/**
 * A quiet global "Offline" chip in the app header (docs/07 §offline). Shows only when connectivity
 * drops, so the state is communicated proactively across every surface — not just the logger. The
 * logger's `SyncStatus` still carries the queued-set count; this is the ambient indicator.
 */
export function OfflineIndicator() {
  const online = useOnline();
  if (online) return null;
  return (
    <span className={styles.chip} role="status" aria-live="polite">
      <span className={styles.dot} aria-hidden />
      Offline
    </span>
  );
}
