import type { Metadata } from "next";

import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Offline",
  description: "You're offline.",
};

/**
 * The offline fallback the service worker serves when a navigation can't reach the network and the
 * target page isn't cached (docs/07 §PWA). Static + auth-free so it precaches cleanly. Reassures
 * that logged sets are safe — the offline write-queue (IndexedDB) syncs on reconnect.
 */
export default function OfflinePage() {
  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <span className={styles.icon} aria-hidden>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path
              d="M4 4l16 16M8.5 8.6A7 7 0 003 12m6.9-4.7A9 9 0 0121 12M6.5 12a4.5 4.5 0 013-1.3M12 20h.01"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          </svg>
        </span>
        <h1 className={styles.title}>You&rsquo;re offline</h1>
        <p className={styles.body}>
          Reconnect to browse the library and dashboard. Any sets you log stay saved on this device
          and sync automatically once you&rsquo;re back online.
        </p>
      </div>
    </div>
  );
}
