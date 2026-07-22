import Link from "next/link";

import { Button, EmptyState } from "@/components/ui";

/** Shown when a Library slug doesn't resolve to a visible exercise. */
export default function ExerciseNotFound() {
  return (
    <EmptyState
      titleAs="h1"
      title="Exercise not found"
      description="That exercise doesn't exist or isn't in your catalog. Head back to browse the full library."
      action={
        <Link href="/library">
          <Button variant="primary">Back to library</Button>
        </Link>
      }
    />
  );
}
