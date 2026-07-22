import { forwardRef } from "react";

import { cn } from "@/lib/cn";
import { Spinner } from "./Spinner";
import styles from "./Button.module.css";

type Variant = "primary" | "outline" | "ghost";
type Size = "sm" | "md";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  fullWidth?: boolean;
}

/**
 * The pill button — the x.ai signature interactive shape (DESIGN.md). `primary` is the rare
 * accent-filled pill; `outline` is the canonical translucent-outline pill; `ghost` is chromeless.
 * Press feedback is a cheap transform (docs/08 §4); disabled/loading states included.
 *
 * A shared (non-"use client") component: server code renders it statically; client code adds
 * `onClick`. See `Pressable`/`ExerciseCard` for spring-driven press on larger surfaces.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "outline",
    size = "md",
    loading = false,
    fullWidth = false,
    disabled,
    className,
    children,
    type = "button",
    ...props
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        styles.button,
        styles[variant],
        styles[size],
        fullWidth && styles.fullWidth,
        className,
      )}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && <Spinner className={styles.spinner} />}
      <span className={cn(loading && styles.hiddenLabel)}>{children}</span>
    </button>
  );
});
