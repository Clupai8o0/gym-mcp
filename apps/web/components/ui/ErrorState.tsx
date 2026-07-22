import { cn } from "@/lib/cn";
import styles from "./ErrorState.module.css";

export interface ErrorStateProps {
  title?: string;
  description?: string;
  /** Primary recovery control (e.g. a "Try again" Button). */
  action?: React.ReactNode;
  /** Optional secondary control (e.g. a link back to a safe surface). */
  secondaryAction?: React.ReactNode;
  className?: string;
}

/** A quiet alert-triangle for the error surface — danger-toned, tokens only. */
function AlertGlyph() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 4.5 21 20H3L12 4.5Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M12 10v4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="12" cy="17" r="1" fill="currentColor" />
    </svg>
  );
}

/**
 * The canonical error surface (docs/08 rubric §4: every data surface needs an error state). Shared
 * by the route `error.tsx` boundaries and any inline failure. Tokens-only, danger-toned, and
 * presentational (no client hooks) so it renders inside both server and client trees.
 */
export function ErrorState({
  title = "Something went wrong",
  description = "This is usually temporary. Try again in a moment.",
  action,
  secondaryAction,
  className,
}: ErrorStateProps) {
  return (
    <div className={cn(styles.root, className)} role="alert">
      <span className={styles.icon} aria-hidden>
        <AlertGlyph />
      </span>
      <h2 className={styles.title}>{title}</h2>
      {description && <p className={styles.description}>{description}</p>}
      {(action || secondaryAction) && (
        <div className={styles.actions}>
          {action}
          {secondaryAction}
        </div>
      )}
    </div>
  );
}
