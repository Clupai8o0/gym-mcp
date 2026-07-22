import { Skeleton } from "@/components/ui";
import styles from "./loading.module.css";

/** Instant loading state for the Skills board while the overview renders (docs/07 CWV). */
export default function SkillsLoading() {
  return (
    <div className={styles.page} aria-busy="true" aria-label="Loading skills">
      <div className={styles.head}>
        <Skeleton width="6rem" height="0.75rem" />
        <Skeleton width="8rem" height="2rem" />
        <Skeleton width="min(30rem, 100%)" height="1rem" />
      </div>
      <Skeleton width="14rem" height="2.25rem" radius="var(--radius-full)" />
      <div className={styles.grid}>
        {Array.from({ length: 9 }).map((_, index) => (
          <div key={index} className={styles.card}>
            <Skeleton width="5rem" height="5rem" radius="var(--radius-full)" />
            <Skeleton width="70%" height="0.875rem" />
            <Skeleton width="50%" height="0.75rem" />
          </div>
        ))}
      </div>
    </div>
  );
}
