import Link from "next/link";

import { Badge } from "@/components/ui";
import { Pressable } from "@/components/motion/Pressable";
import { titleCase } from "@/lib/format";
import type { ThemePreference } from "@/lib/theme";
import type { Exercise } from "@/lib/types";
import { IllustrationView } from "./IllustrationView";
import styles from "./ExerciseCard.module.css";

/**
 * A catalog tile: illustration + name + primary-muscle/equipment tags, linking to the detail
 * page. The illustration carries a shared-element name so it morphs into the detail hero
 * (docs/08). `Pressable` adds the press-scale. `priority` eager-loads the above-the-fold LCP tiles.
 *
 * Synchronous, and takes the theme `preference` as a prop rather than reading the cookie itself —
 * the grid resolves it once on the server and hands it down, which is what lets the same card
 * render both the server's first page and the pages the client appends on scroll.
 */
export function ExerciseCard({
  exercise,
  preference,
  priority = false,
}: {
  exercise: Exercise;
  preference: ThemePreference;
  priority?: boolean;
}) {
  const primaryMuscle = exercise.primary_muscles[0];
  return (
    <Link href={`/library/${exercise.slug}`} className={styles.link} prefetch={false}>
      <Pressable className={styles.pressable}>
        <article className={styles.card}>
          <IllustrationView
            url={exercise.illustration_url}
            urlLight={exercise.illustration_url_light}
            status={exercise.illustration_status}
            name={exercise.name}
            preference={preference}
            shareName={`exercise-illustration-${exercise.slug}`}
            priority={priority}
          />
          <div className={styles.body}>
            <h3 className={styles.name}>{exercise.name}</h3>
            <div className={styles.meta}>
              {primaryMuscle && <Badge tone="muscle">{titleCase(primaryMuscle)}</Badge>}
              {exercise.equipment && <Badge>{titleCase(exercise.equipment)}</Badge>}
              {exercise.is_custom && <Badge tone="custom">Custom</Badge>}
            </div>
          </div>
        </article>
      </Pressable>
    </Link>
  );
}
