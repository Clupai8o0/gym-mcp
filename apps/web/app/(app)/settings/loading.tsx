import { Skeleton } from "@/components/ui";
import styles from "./loading.module.css";

/** Instant loading state for Settings while the account + connections render (docs/07 CWV). */
export default function SettingsLoading() {
  return (
    <div className={styles.page} aria-busy="true" aria-label="Loading settings">
      <div className={styles.head}>
        <Skeleton width="5rem" height="0.75rem" />
        <Skeleton width="9rem" height="2rem" />
      </div>
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className={styles.section}>
          <Skeleton width="11rem" height="1.25rem" />
          <Skeleton width="100%" height="5.5rem" radius="var(--radius-lg)" />
        </div>
      ))}
    </div>
  );
}
