import { Skeleton } from "@/components/ui";
import styles from "../loading.module.css";

/** Instant loading state for /progress/records (docs/07 CWV). */
export default function Loading() {
  return (
    <div className={styles.page} aria-busy="true" aria-label="Loading records">
      <div className={styles.head}>
        <div className={styles.titleBlock}>
          <Skeleton width="5rem" height="0.75rem" />
          <Skeleton width="10rem" height="2rem" />
          <Skeleton width="min(30rem, 100%)" height="1rem" />
        </div>
      </div>
      <Skeleton className={styles.block} />
    </div>
  );
}
