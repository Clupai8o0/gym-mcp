import { cn } from "@/lib/cn";
import type { Art } from "./art";
import { BENCH_SIT, LOCKOUT } from "./art";
import styles from "./Illustration.module.css";

/**
 * Paints one illustration from its two masks.
 *
 * Two stacked layers rather than an `<img>`: the body layer is filled with `--ill-ink` and the
 * implement layer with `--accent`, so colour comes from tokens at render time instead of being
 * baked into the file. Same reason the exercise line art is authored monochrome (docs/06) — the
 * app decides what surface it lands on, not the asset.
 *
 * Decorative. `aria-hidden` on the wrapper; anything the drawing says is said in the copy beside
 * it, and the movement sheet captions its cells in real text.
 *
 * Server component, and static: the drawings carry no entrance animation, so a figure is simply
 * there when its section is.
 */
export function Illustration({ art, className }: { art: Art; className?: string }) {
  return (
    <div className={cn(styles.figure, className)} style={{ aspectRatio: art.ratio }} aria-hidden>
      <span
        className={styles.ink}
        style={{ "--ill-mask": `url(/illustrations/${art.name}-ink.webp)` } as React.CSSProperties}
      />
      {art.accent ? (
        <span
          className={styles.accent}
          style={
            { "--ill-mask": `url(/illustrations/${art.name}-accent.webp)` } as React.CSSProperties
          }
        />
      ) : null}
    </div>
  );
}

/* Named placements, so the page reads as what it shows rather than as asset basenames. */

/** Logging: sat on the end of a bench between sets, phone in hand. The accent is on the log. */
export function BetweenSets({ className }: { className?: string }) {
  return <Illustration art={BENCH_SIT} className={className} />;
}

/** Final CTA: the bar that opened the page at the hang, now locked out overhead. */
export function Lockout({ className }: { className?: string }) {
  return <Illustration art={LOCKOUT} className={className} />;
}
