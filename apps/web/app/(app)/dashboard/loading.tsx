import { Skeleton } from "@/components/ui";
import styles from "./loading.module.css";

/** Instant loading state for the Dashboard while analytics render (docs/07 CWV). */
export default function DashboardLoading() {
  return (
    <div className={styles.page} aria-busy="true" aria-label="Loading dashboard">
      <div className={styles.head}>
        <div className={styles.titleBlock}>
          <Skeleton width="5rem" height="0.75rem" />
          <Skeleton width="12rem" height="2rem" />
        </div>
        <Skeleton width="14rem" height="2.25rem" radius="var(--radius-full)" />
      </div>
      <Skeleton width="16rem" height="1.5rem" />
      <div className={styles.cards}>
        <Skeleton className={styles.block} />
        <Skeleton className={styles.block} />
      </div>
    </div>
  );
}
