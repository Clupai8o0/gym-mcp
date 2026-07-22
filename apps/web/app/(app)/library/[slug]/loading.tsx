import { Skeleton } from "@/components/ui";
import styles from "./loading.module.css";

/** Partial-prefetch loading state for a Library detail page (docs/07 CWV). */
export default function ExerciseDetailLoading() {
  return (
    <div className={styles.page} aria-busy="true" aria-label="Loading exercise">
      <Skeleton width="6rem" height="1rem" />
      <div className={styles.layout}>
        <Skeleton className={styles.media} />
        <div className={styles.content}>
          <Skeleton width="9rem" height="0.75rem" />
          <Skeleton width="70%" height="2.5rem" />
          <div className={styles.tags}>
            <Skeleton width="5rem" height="1.5rem" radius="var(--radius-full)" />
            <Skeleton width="6rem" height="1.5rem" radius="var(--radius-full)" />
          </div>
          <Skeleton width="12rem" height="2.5rem" radius="var(--radius-full)" />
        </div>
      </div>
    </div>
  );
}
