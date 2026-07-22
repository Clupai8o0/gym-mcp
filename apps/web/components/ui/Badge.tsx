import { cn } from "@/lib/cn";
import styles from "./Badge.module.css";

type Tone = "neutral" | "accent" | "muscle" | "custom";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

/** Small pill tag for muscle/equipment/category metadata (docs/08 `Badge/Tag`). */
export function Badge({ tone = "neutral", className, children, ...props }: BadgeProps) {
  return (
    <span className={cn(styles.badge, styles[tone], className)} {...props}>
      {children}
    </span>
  );
}
