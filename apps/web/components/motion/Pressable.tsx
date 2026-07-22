import { cn } from "@/lib/cn";
import styles from "./Pressable.module.css";

export interface PressableProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * Wraps a larger interactive surface (e.g. `ExerciseCard`, a `SkillRing` tile) with a subtle
 * press-scale. Pure CSS `:active` on a cheap transform (docs/08 §4) — no motion library, so it
 * stays out of the Library/Dashboard initial bundle. Reduced motion neutralizes the press.
 */
export function Pressable({ children, className }: PressableProps) {
  return <div className={cn(styles.pressable, className)}>{children}</div>;
}
