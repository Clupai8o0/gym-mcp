import { ridgeLines } from "./trainingSeries";
import styles from "./RidgeField.module.css";

/**
 * The hero backdrop: half a year of training drawn as thirteen stacked fortnights, oldest at the
 * top. Height is that day's effort, the flat stretches are rest days, and the lines run grey at
 * the far end of the block to full accent at this week.
 *
 * Decorative, so `aria-hidden`. Everything it conveys is stated in the hero copy and caption
 * beside it, and the dashboard preview further down the page shows the same information in a
 * labelled, readable form. A masked backdrop is dimmed so the headline stays legible, and that
 * dimming is exactly what stops it being decodable, so it is not asked to carry meaning here.
 *
 * Server component. No client JS, and the paths are precomputed at module load.
 */
export function RidgeField() {
  return (
    <svg className={styles.svg} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
      {ridgeLines.map((line) => (
        <path
          key={line.row}
          className={styles.line}
          d={line.d}
          vectorEffect="non-scaling-stroke"
          style={
            {
              "--mix": line.mix,
              "--line-opacity": line.opacity,
              "--enter-delay": `${line.row * 45}ms`,
            } as React.CSSProperties
          }
        />
      ))}
    </svg>
  );
}
