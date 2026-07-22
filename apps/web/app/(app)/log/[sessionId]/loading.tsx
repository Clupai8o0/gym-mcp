import { Skeleton } from "@/components/ui";
import styles from "./loading.module.css";

/** Instant loading state for a session while its detail renders (docs/07 CWV). */
export default function SessionLoading() {
  return (
    <div className={styles.page} aria-busy="true" aria-label="Loading workout">
      <div className={styles.head}>
        <Skeleton width="6rem" height="0.75rem" />
        <Skeleton width="14rem" height="2rem" />
        <Skeleton width="10rem" height="0.875rem" />
      </div>
      {Array.from({ length: 2 }).map((_, index) => (
        <div key={index} className={styles.block}>
          <Skeleton width="40%" height="1.25rem" />
          <Skeleton width="100%" height="3rem" radius="var(--radius-md)" />
          <Skeleton width="100%" height="8rem" radius="var(--radius-lg)" />
        </div>
      ))}
    </div>
  );
}
