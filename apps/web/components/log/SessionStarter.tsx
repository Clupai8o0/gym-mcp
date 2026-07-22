"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button, Input } from "@/components/ui";
import { createSession } from "@/lib/client";
import styles from "./SessionStarter.module.css";

export interface SessionStarterProps {
  /** Optional exercise slug to pre-add once the session opens (from the Library "Log this"). */
  exerciseSlug?: string;
  /** `compact` renders just the button (used alongside a "continue today" card). */
  compact?: boolean;
}

/**
 * Starts a new workout (docs/07 §Log). Creates the session via the same `sessions.create` service
 * REST/MCP use, then navigates to its logging surface. An optional title keeps the common path
 * one tap; a pending exercise slug is forwarded so it's pre-added on arrival.
 */
export function SessionStarter({ exerciseSlug, compact = false }: SessionStarterProps) {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      const session = await createSession({
        performed_at: new Date().toISOString(),
        title: title.trim() || null,
      });
      const suffix = exerciseSlug ? `?add=${encodeURIComponent(exerciseSlug)}` : "";
      router.push(`/log/${session.id}${suffix}`);
    } catch {
      setError("Couldn’t start a workout. Check your connection and try again.");
      setStarting(false);
    }
  };

  if (compact) {
    return (
      <Button variant="outline" onClick={start} loading={starting}>
        Start another workout
      </Button>
    );
  }

  return (
    <div className={styles.starter}>
      <Input
        aria-label="Workout name (optional)"
        placeholder="Name this workout (optional)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className={styles.input}
        maxLength={200}
      />
      <Button variant="primary" onClick={start} loading={starting} className={styles.button}>
        Start workout
      </Button>
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
