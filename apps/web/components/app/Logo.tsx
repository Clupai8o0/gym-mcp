import { cn } from "@/lib/cn";
import styles from "./Logo.module.css";

/**
 * The Tempo mark — three sunset "tempo" bars, the same geometry as the app icon (`public/icon.svg`
 * + the generated PWA icons). Decorative: it always sits beside the "Tempo" wordmark, so it's
 * `aria-hidden` and the surrounding link/label carries the accessible name.
 */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 512 512" className={cn(styles.logo, className)} aria-hidden>
      <g fill="currentColor">
        <rect x="150" y="240" width="40" height="132" rx="20" />
        <rect x="236" y="150" width="40" height="222" rx="20" />
        <rect x="322" y="196" width="40" height="176" rx="20" />
      </g>
    </svg>
  );
}
