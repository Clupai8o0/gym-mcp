import { Skeleton } from "@/components/ui";
import styles from "./loading.module.css";

/** Instant loading state for Home — mirrors the summary column's block rhythm (docs/07 CWV). */
export default function HomeLoading() {
  return (
    <div className={styles.page} aria-busy="true" aria-label="Loading home">
      <div className={styles.head}>
        <div className={styles.titleBlock}>
          <Skeleton width="9rem" height="0.75rem" />
          <Skeleton width="7rem" height="1.75rem" />
        </div>
        <Skeleton width="2.25rem" height="2.25rem" radius="var(--radius-full)" />
      </div>

      <Skeleton className={styles.workout} />

      <div className={styles.stats}>
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className={styles.stat} />
        ))}
      </div>

      <Skeleton className={styles.strip} />
      <Skeleton className={styles.row} />
      <Skeleton className={styles.row} />
    </div>
  );
}
