import { cn } from "@/lib/cn";
import styles from "./Reveal.module.css";

/**
 * Scroll-triggered enter for marketing sections. CSS-only, using `animation-timeline: view()`,
 * so there is no IntersectionObserver, no client component and no JS on the critical path. The
 * animation also runs off the main thread, which matters on a page that is otherwise mostly
 * static and should stay smooth while fonts and images are still landing.
 *
 * Authored so that failure is invisible: the resting state is the *visible* one, and the reveal
 * is applied only inside `@supports (animation-timeline: view())`. A browser without support
 * (Firefox at time of writing) simply shows the content, rather than hiding it forever waiting
 * for an animation that will never run. Reduced motion opts out the same way.
 */
export function Reveal({
  as: Tag = "div",
  delay = 0,
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLElement> & {
  as?: "div" | "section" | "li";
  /** Stagger offset in ms, applied as an animation-delay on the reveal. */
  delay?: number;
}) {
  return (
    <Tag
      className={cn(styles.reveal, className)}
      style={delay ? ({ "--reveal-delay": `${delay}ms` } as React.CSSProperties) : undefined}
      {...props}
    >
      {children}
    </Tag>
  );
}
