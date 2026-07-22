import { cn } from "@/lib/cn";
import styles from "./FadeIn.module.css";

export interface FadeInProps extends React.HTMLAttributes<HTMLElement> {
  /** Stagger offset in ms (applied as animation-delay). */
  delay?: number;
  as?: "div" | "li" | "section";
}

/**
 * Enter primitive: a fast opacity + small upward move on mount, decelerating (docs/08 §2–3).
 * Pure CSS (transform/opacity only — GPU-friendly, no layout thrash); the global reduced-motion
 * rule collapses it to an instant appear. No client JS.
 */
export function FadeIn({
  delay = 0,
  as = "div",
  className,
  style,
  children,
  ...props
}: FadeInProps) {
  const Tag = as;
  return (
    <Tag
      className={cn(styles.fadeIn, className)}
      style={{ animationDelay: delay ? `${delay}ms` : undefined, ...style }}
      {...props}
    >
      {children}
    </Tag>
  );
}
