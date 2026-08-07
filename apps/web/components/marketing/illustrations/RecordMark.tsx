import styles from "./RecordMark.module.css";

/**
 * The three getting-started steps, drawn as the thing the steps produce: a record that is two
 * bars long after you sign in, five after your first session, and still growing by the third.
 *
 * The one drawing on the page that stays SVG rather than a mask pair. It is a chart, not a
 * figure — nine hairlines whose exact heights carry the meaning — so vector is both smaller and
 * sharper than any raster of it, and the geometry is worth reading in the source.
 *
 * The last bar of the last step takes the accent, because that one is this week.
 */
const SERIES: number[][] = [
  [6, 9],
  [6, 9, 7, 12, 10],
  [6, 9, 7, 12, 10, 14, 11, 16, 19],
];

export function RecordMark({ step }: { step: 0 | 1 | 2 }) {
  const bars = SERIES[step];
  const last = bars.length - 1;
  return (
    <svg viewBox="0 0 72 24" className={styles.svg} aria-hidden>
      {bars.map((height, index) => (
        <path
          key={index}
          className={step === 2 && index === last ? styles.accent : styles.ink}
          d={`M${3 + index * 8} 22V${22 - height}`}
        />
      ))}
    </svg>
  );
}
