import styles from "./Spinner.module.css";
import { cn } from "@/lib/cn";

/** A minimal token-driven loading spinner. Decorative by default (aria-hidden). */
export function Spinner({ className, label }: { className?: string; label?: string }) {
  return (
    <span
      className={cn(styles.spinner, className)}
      role={label ? "status" : undefined}
      aria-hidden={label ? undefined : true}
      aria-label={label}
    />
  );
}
