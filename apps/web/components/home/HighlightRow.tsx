import Link from "next/link";

import styles from "./HighlightRow.module.css";

export interface HighlightRowProps {
  /** Mono eyebrow — "Latest PR", "Top skill". */
  eyebrow: string;
  title: string;
  /** The number that matters, right-aligned and tabular. */
  value: string;
  /** Small muted line under the value (a date, a stage). */
  meta?: React.ReactNode;
  href: string;
}

/**
 * One line of "here's the good bit" — the latest personal record, the strongest skill. A row
 * rather than a card because home's whole budget is one phone screen: these are the two things
 * worth surfacing, and each is a pointer to the full list rather than the list itself.
 */
export function HighlightRow({ eyebrow, title, value, meta, href }: HighlightRowProps) {
  return (
    <Link href={href} className={styles.row}>
      <span className={styles.text}>
        <span className={`eyebrow ${styles.eyebrow}`}>{eyebrow}</span>
        <span className={styles.title}>{title}</span>
      </span>
      <span className={styles.right}>
        <span className={`${styles.value} tnum`}>{value}</span>
        {meta && <span className={styles.meta}>{meta}</span>}
      </span>
      <span className={styles.chevron} aria-hidden>
        →
      </span>
    </Link>
  );
}
