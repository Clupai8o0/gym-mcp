import Link from "next/link";

import { Badge } from "@/components/ui";
import { Pressable } from "@/components/motion/Pressable";
import { titleCase } from "@/lib/format";
import type { Exercise } from "@/lib/types";
import { IllustrationImage } from "./IllustrationImage";
import styles from "./ExerciseCard.module.css";

/**
 * A catalog tile: illustration + name + primary-muscle/equipment tags, linking to the detail
 * page. The illustration carries a shared-element name so it morphs into the detail hero
 * (docs/08). Server-rendered; `Pressable` adds the press-scale. `priority` eager-loads the
 * above-the-fold LCP tiles.
 */
export function ExerciseCard({ exercise, priority = false }: { exercise: Exercise; priority?: boolean }) {
  const primaryMuscle = exercise.primary_muscles[0];
  return (
    <Link href={`/library/${exercise.slug}`} className={styles.link} prefetch={false}>
      <Pressable className={styles.pressable}>
        <article className={styles.card}>
          <IllustrationImage
            url={exercise.illustration_url}
            status={exercise.illustration_status}
            name={exercise.name}
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
