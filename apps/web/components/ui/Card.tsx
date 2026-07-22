import { cn } from "@/lib/cn";
import styles from "./Card.module.css";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** `interactive` adds hover affordance for clickable cards. */
  interactive?: boolean;
  padded?: boolean;
}

/** The default surface: `--surface` fill, hairline border, no shadow (DESIGN.md elevation). */
export function Card({
  interactive = false,
  padded = true,
  className,
  children,
  ...props
}: CardProps) {
  return (
    <div
      className={cn(
        styles.card,
        interactive && styles.interactive,
        padded && styles.padded,
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}
