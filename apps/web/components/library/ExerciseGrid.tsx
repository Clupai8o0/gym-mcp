import { Stagger } from "@/components/motion/Stagger";
import type { Exercise } from "@/lib/types";
import { ExerciseCard } from "./ExerciseCard";
import styles from "./ExerciseGrid.module.css";

/** The catalog grid — server-rendered cards with a subtle staggered entrance (docs/08 §8). */
export function ExerciseGrid({ exercises }: { exercises: Exercise[] }) {
  return (
    <Stagger className={styles.grid}>
      {exercises.map((exercise, index) => (
        // Eager-load the first row (the LCP candidates); the rest lazy-load on scroll (docs/07 CWV).
        <ExerciseCard key={exercise.id} exercise={exercise} priority={index < 6} />
      ))}
    </Stagger>
  );
}
