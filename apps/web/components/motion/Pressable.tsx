"use client";

import { motion, useReducedMotion } from "motion/react";

import { spring } from "@/design/motion";

export interface PressableProps {
  children: React.ReactNode;
  className?: string;
  /** Scale at the bottom of the press (docs/08 §3: spring for grabbed things). */
  pressScale?: number;
}

/**
 * Wraps interactive surfaces with an interruptible spring press (docs/08 §3, §6). Used on larger
 * targets like `ExerciseCard`; small buttons use the CSS `:active` scale instead. Under reduced
 * motion the press is neutralized (no transform).
 */
export function Pressable({ children, className, pressScale = 0.98 }: PressableProps) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      whileTap={reduce ? undefined : { scale: pressScale }}
      transition={spring}
    >
      {children}
    </motion.div>
  );
}
