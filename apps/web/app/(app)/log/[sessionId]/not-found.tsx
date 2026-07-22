import Link from "next/link";

import { Button, EmptyState } from "@/components/ui";

/** A session id that isn't the user's (or was deleted) resolves here (docs/07 auth-scoped reads). */
export default function SessionNotFound() {
  return (
    <EmptyState
      titleAs="h1"
      title="Workout not found"
      description="This session doesn’t exist or isn’t yours. Start a new one to begin logging."
      action={
        <Link href="/log">
          <Button variant="primary">Back to Log</Button>
        </Link>
      }
    />
  );
}
