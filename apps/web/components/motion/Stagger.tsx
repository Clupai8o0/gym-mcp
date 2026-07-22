import { Children, isValidElement } from "react";

import { FadeIn } from "./FadeIn";

export interface StaggerProps {
  children: React.ReactNode;
  /** Per-item delay step in ms (docs/08 §8: subtle 20–40ms). */
  step?: number;
  /** Cap how many items are staggered so long lists don't wait (rest share the last delay). */
  max?: number;
  className?: string;
  as?: "div" | "ul";
  itemAs?: "div" | "li";
}

/**
 * Choreographs a list of children into a subtle staggered enter, guiding the eye without
 * everything moving at once (docs/08 §8). Wraps each child in {@link FadeIn} with an increasing
 * delay. Server-friendly (no hooks); reduced motion collapses each item to an instant appear.
 */
export function Stagger({
  children,
  step = 28,
  max = 12,
  className,
  as = "div",
  itemAs = "div",
}: StaggerProps) {
  const Wrapper = as;
  return (
    <Wrapper className={className}>
      {Children.map(children, (child, index) => {
        if (!isValidElement(child)) return child;
        const delay = Math.min(index, max) * step;
        return (
          <FadeIn as={itemAs} delay={delay}>
            {child}
          </FadeIn>
        );
      })}
    </Wrapper>
  );
}
