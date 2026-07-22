import { cn } from "@/lib/cn";
import styles from "./Skeleton.module.css";

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  /** CSS width/height (token or length). */
  width?: string;
  height?: string;
  radius?: string;
}

/** Shimmer placeholder for loading states. Decorative (aria-hidden); shimmer respects RM. */
export function Skeleton({ width, height, radius, className, style, ...props }: SkeletonProps) {
  return (
    <div
      aria-hidden
      className={cn(styles.skeleton, className)}
      style={{ width, height, borderRadius: radius, ...style }}
      {...props}
    />
  );
}
