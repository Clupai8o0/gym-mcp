"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui";
import { finishSession } from "@/lib/client";
import { formatDuration } from "@/lib/format";
import styles from "./FinishWorkout.module.css";

export interface FinishWorkoutProps {
  sessionId: string;
  /** Already-stamped end time, if the workout was finished earlier (server-rendered). */
  endedAt: string | null;
  /** Stored duration for a finished workout. */
  durationMinutes: number | null;
  /** Sets still waiting in the offline queue — flagged so nothing looks lost. */
  pending?: number;
}

/**
 * Ends the workout (Phase 11A). Closing a session is what makes it stop counting as "in
 * progress" everywhere else — the tab badge, the session bar, `/log` — so this is the one
 * control that has to be obvious and always reachable. The server is idempotent, so a
 * double-tap or a retried request can't corrupt the duration.
 */
export function FinishWorkout({
  sessionId,
  endedAt,
  durationMinutes,
  pending = 0,
}: FinishWorkoutProps) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [finished, setFinished] = useState<{ duration: number | null } | null>(
    endedAt ? { duration: durationMinutes } : null,
  );

  const finish = async () => {
    setBusy(true);
    setError(null);
    try {
      const session = await finishSession(sessionId);
      setFinished({ duration: session.duration_minutes });
      router.refresh();
    } catch {
      setError("Couldn’t finish the workout. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  };

  if (finished) {
    return (
      <p className={styles.done}>
        <span className={styles.check} aria-hidden>
          ✓
        </span>
        Workout finished
        {finished.duration != null ? ` · ${formatDuration(finished.duration)}` : ""}
      </p>
    );
  }

  return (
    <div className={styles.wrap}>
      <Button variant="outline" onClick={finish} loading={busy}>
        Finish workout
      </Button>
      {pending > 0 && (
        <p className={styles.note}>
          {pending} set{pending === 1 ? "" : "s"} still syncing — they’ll land in this workout.
        </p>
      )}
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
