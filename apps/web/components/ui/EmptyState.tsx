import { cn } from "@/lib/cn";
import styles from "./EmptyState.module.css";

export interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

/** Tasteful empty/no-results state (docs/08 `EmptyState`). */
export function EmptyState({ title, description, icon, action, className }: EmptyStateProps) {
  return (
    <div className={cn(styles.root, className)}>
      {icon && (
        <div className={styles.icon} aria-hidden>
          {icon}
        </div>
      )}
      <h2 className={styles.title}>{title}</h2>
      {description && <p className={styles.description}>{description}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
