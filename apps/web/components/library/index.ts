/**
 * Server-facing barrel: `IllustrationImage` pulls in `next/headers`, so importing this file from a
 * client component would drag server-only code into the browser bundle. Client code imports the
 * modules it needs directly (`./IllustrationView`, `./ExerciseGrid`).
 */
export { ExerciseCard } from "./ExerciseCard";
export { ExerciseGrid } from "./ExerciseGrid";
export { FilterBar } from "./FilterBar";
export { InfiniteExerciseGrid } from "./InfiniteExerciseGrid";
export { IllustrationImage } from "./IllustrationImage";
