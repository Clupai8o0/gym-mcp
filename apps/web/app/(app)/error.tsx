"use client";

import { useEffect } from "react";
import Link from "next/link";

import { Button, ErrorState } from "@/components/ui";
import styles from "./error.module.css";

/**
 * Error boundary for the authenticated app segment (docs/08 rubric §4). Renders inside the app
 * shell — the header stays anchored — so a failed Dashboard/Library/Log/Settings render degrades
 * to a recoverable state instead of a blank screen. `unstable_retry` re-fetches + re-renders the
 * segment (Next 16.2); `reset` is the pre-16.2 fallback.
 */
export default function AppError({
  error,
  unstable_retry,
  reset,
}: {
  error: Error & { digest?: string };
  unstable_retry?: () => void;
  reset?: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  const retry = unstable_retry ?? reset;

  return (
    <div className={styles.wrap}>
      <ErrorState
        description="We couldn't load this page. Your data is safe — this is usually a temporary hiccup."
        action={
          retry ? (
            <Button variant="primary" onClick={() => retry()}>
              Try again
            </Button>
          ) : undefined
        }
        secondaryAction={
          <Link href="/library">
            <Button variant="outline">Back to library</Button>
          </Link>
        }
      />
    </div>
  );
}
