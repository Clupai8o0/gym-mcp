import { Skeleton } from "@/components/ui";
import gridStyles from "@/components/library/ExerciseGrid.module.css";
import styles from "./loading.module.css";

/** Instant loading state for the Library while the catalog page renders (docs/07 CWV). */
export default function LibraryLoading() {
  return (
    <div className={styles.page} aria-busy="true" aria-label="Loading exercises">
      <div className={styles.head}>
        <Skeleton width="8rem" height="0.75rem" />
        <Skeleton width="16rem" height="2rem" />
      </div>
      <Skeleton width="100%" height="2.5rem" radius="var(--radius-md)" />
      <div className={gridStyles.grid}>
        {Array.from({ length: 12 }).map((_, index) => (
          <div key={index} className={styles.card}>
            <Skeleton className={styles.thumb} />
            <Skeleton width="80%" height="1rem" />
            <Skeleton width="55%" height="0.75rem" />
          </div>
        ))}
      </div>
    </div>
  );
}
