import { Skeleton } from "@/components/ui";
import styles from "./loading.module.css";

/** Instant loading state for the Log home while recent sessions render (docs/07 CWV). */
export default function LogLoading() {
  return (
    <div className={styles.page} aria-busy="true" aria-label="Loading">
      <div className={styles.head}>
        <Skeleton width="7rem" height="0.75rem" />
        <Skeleton width="14rem" height="2rem" />
        <Skeleton width="min(26rem, 100%)" height="1rem" />
      </div>
      <Skeleton width="100%" height="6rem" radius="var(--radius-lg)" />
      <div className={styles.recent}>
        <Skeleton width="10rem" height="1.25rem" />
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} width="100%" height="4.5rem" radius="var(--radius-md)" />
        ))}
      </div>
    </div>
  );
}
