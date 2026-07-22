import { cn } from "@/lib/cn";
import styles from "./EmptyState.module.css";

export interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  /** Heading level for the title — use `h1` when this state IS the whole page (a not-found). */
  titleAs?: "h1" | "h2";
  className?: string;
}

/** Tasteful empty/no-results state (docs/08 `EmptyState`). */
export function EmptyState({
  title,
  description,
  icon,
  action,
  titleAs: TitleTag = "h2",
  className,
}: EmptyStateProps) {
  return (
    <div className={cn(styles.root, className)}>
      {icon && (
        <div className={styles.icon} aria-hidden>
          {icon}
        </div>
      )}
      <TitleTag className={styles.title}>{title}</TitleTag>
      {description && <p className={styles.description}>{description}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
