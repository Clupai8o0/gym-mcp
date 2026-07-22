"use client";

import { useEffect } from "react";

import { Button, ErrorState } from "@/components/ui";
import "./globals.css";
import styles from "./global-error.module.css";

/**
 * Last-resort boundary — catches errors in the root layout itself, replacing the whole document
 * (so it must ship its own <html>/<body>). `metadata` isn't supported here, so the tab title is a
 * plain <title> (Next 16 file-conventions/error). Tokens + reset come from the imported globals.
 */
export default function GlobalError({
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
    <html lang="en">
      <title>Something went wrong · Tempo</title>
      <body className={styles.body}>
        <div className={styles.wrap}>
          <ErrorState
            title="Something went wrong"
            description="Tempo hit an unexpected error. Reloading usually clears it."
            action={
              <Button
                variant="primary"
                onClick={() => (retry ? retry() : window.location.reload())}
              >
                Reload
              </Button>
            }
          />
        </div>
      </body>
    </html>
  );
}
