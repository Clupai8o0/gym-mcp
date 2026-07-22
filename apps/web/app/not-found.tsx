import Link from "next/link";

import { Button, EmptyState } from "@/components/ui";
import styles from "./not-found.module.css";

/** Branded 404 for unmatched routes (renders with the root layout — no app chrome). */
export default function NotFound() {
  return (
    <div className={styles.wrap}>
      <div className={styles.inner}>
        <EmptyState
          titleAs="h1"
          title="Page not found"
          description="The page you're looking for doesn't exist or has moved."
          action={
            <Link href="/">
              <Button variant="primary">Back to home</Button>
            </Link>
          }
        />
      </div>
    </div>
  );
}
