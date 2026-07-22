import { Stagger } from "@/components/motion/Stagger";
import type { Exercise } from "@/lib/types";
import { ExerciseCard } from "./ExerciseCard";
import styles from "./ExerciseGrid.module.css";

/** The catalog grid — server-rendered cards with a subtle staggered entrance (docs/08 §8). */
export function ExerciseGrid({ exercises }: { exercises: Exercise[] }) {
  return (
    <Stagger className={styles.grid}>
      {exercises.map((exercise) => (
        <ExerciseCard key={exercise.id} exercise={exercise} />
      ))}
    </Stagger>
  );
}
