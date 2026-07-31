"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Button, LocalTime } from "@/components/ui";
import { FadeIn } from "@/components/motion/FadeIn";
import { ClientApiError, deleteSet as apiDeleteSet, getExerciseBySlug } from "@/lib/client";
import { useOfflineQueue } from "@/lib/offline/useOfflineQueue";
import { removeQueuedSet } from "@/lib/offline/queue";
import type { Exercise, LoggedSet, SessionDetail, SetCreate, UnitPref } from "@/lib/types";
import { ExerciseBlock } from "./ExerciseBlock";
import { ExercisePicker } from "./ExercisePicker";
import { FinishWorkout } from "./FinishWorkout";
import { RestTimer } from "./RestTimer";
import { SyncStatus } from "./SyncStatus";
import type { LogGroup, LogSet, SetDraft } from "./types";
import styles from "./SessionLogger.module.css";

export interface SessionLoggerProps {
  session: SessionDetail;
  unitPref: UnitPref;
}

/** How long the PR bloom plays before it's cleared — comfortably longer than the ~420ms animation. */
const CELEBRATE_MS = 900;

/** Seed the client view model from the server's session detail (all sets already persisted). */
function seedGroups(session: SessionDetail): LogGroup[] {
  return session.exercises.map((group) => ({
    exercise: group.exercise,
    sets: group.sets.map((s): LogSet => ({
      clientId: s.id,
      serverId: s.id,
      setNumber: s.set_number,
      weightKg: s.weight_kg,
      reps: s.reps,
      holdSeconds: s.hold_seconds,
      rpe: s.rpe,
      status: "saved",
      isPr: s.is_pr,
      prType: s.pr_type,
      prValue: null,
      prUnit: null,
    })),
  }));
}

function toPayload(exerciseId: string, set: LogSet): SetCreate {
  return {
    exercise_id: exerciseId,
    set_number: set.setNumber,
    weight_kg: set.weightKg,
    reps: set.reps,
    hold_seconds: set.holdSeconds,
    rpe: set.rpe,
  };
}

function maxSetNumber(group: LogGroup | undefined): number {
  if (!group) return 0;
  return group.sets
    .filter((s) => s.status !== "error")
    .reduce((max, s) => Math.max(max, s.setNumber), 0);
}

/**
 * The active-session logging surface (docs/07 §Log): add exercises, log sets with optimistic
 * saves, PR celebrations, offline queuing, and a rest timer. All writes go through the same
 * `sessions`/`sets` services REST and MCP use — so a set logged here is byte-identical to one
 * logged from chat (verified by the Phase 5 MCP↔REST contract tests).
 */
export function SessionLogger({ session, unitPref }: SessionLoggerProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [groups, setGroups] = useState<LogGroup[]>(() => seedGroups(session));
  const [pickerOpen, setPickerOpen] = useState(false);
  const [celebrateId, setCelebrateId] = useState<string | null>(null);
  const [restKey, setRestKey] = useState(0);
  const [restActive, setRestActive] = useState(false);
  const celebrateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── State helpers (immutable, keyed by clientId) ──────────────────────────────────────────
  const patchSet = useCallback((clientId: string, patch: Partial<LogSet>) => {
    setGroups((gs) =>
      gs.map((g) => ({
        ...g,
        sets: g.sets.map((s) => (s.clientId === clientId ? { ...s, ...patch } : s)),
      })),
    );
  }, []);

  const dropSet = useCallback((clientId: string) => {
    setGroups((gs) =>
      gs.map((g) => ({ ...g, sets: g.sets.filter((s) => s.clientId !== clientId) })),
    );
  }, []);

  const celebrate = useCallback((clientId: string) => {
    setCelebrateId(clientId);
    if (celebrateTimer.current) clearTimeout(celebrateTimer.current);
    celebrateTimer.current = setTimeout(() => setCelebrateId(null), CELEBRATE_MS);
  }, []);

  useEffect(
    () => () => {
      if (celebrateTimer.current) clearTimeout(celebrateTimer.current);
    },
    [],
  );

  const applyLogged = useCallback(
    (clientId: string, logged: LoggedSet) => {
      patchSet(clientId, {
        serverId: logged.set.id,
        status: "saved",
        setNumber: logged.set.set_number,
        weightKg: logged.set.weight_kg,
        reps: logged.set.reps,
        holdSeconds: logged.set.hold_seconds,
        rpe: logged.set.rpe,
        isPr: logged.pr.is_pr,
        prType: logged.pr.pr_type,
        prValue: logged.pr.new_value,
      });
      if (logged.pr.is_pr) celebrate(clientId);
    },
    [patchSet, celebrate],
  );

  // ── Offline queue: reconcile writes that synced on reconnect ───────────────────────────────
  const onSyncFailed = useCallback(
    (clientId: string, error: ClientApiError) =>
      patchSet(clientId, { status: "error", errorMessage: error.message }),
    [patchSet],
  );
  const { online, pending, submitSet } = useOfflineQueue({
    onSynced: applyLogged,
    onSyncFailed,
  });

  const submit = useCallback(
    async (exerciseId: string, set: LogSet) => {
      try {
        const outcome = await submitSet({
          clientId: set.clientId,
          sessionId: session.id,
          payload: toPayload(exerciseId, set),
        });
        if (outcome.queued) patchSet(set.clientId, { status: "queued" });
        else applyLogged(set.clientId, outcome.result);
      } catch (error) {
        const message =
          error instanceof ClientApiError ? error.message : "Couldn’t save — tap to retry";
        patchSet(set.clientId, { status: "error", errorMessage: message });
      }
    },
    [submitSet, session.id, patchSet, applyLogged],
  );

  // ── Exercise management ───────────────────────────────────────────────────────────────────
  const addExercise = useCallback((exercise: Exercise) => {
    setGroups((gs) => {
      if (gs.some((g) => g.exercise.id === exercise.id)) return gs;
      return [...gs, { exercise, sets: [] }];
    });
  }, []);

  const removeExercise = useCallback((exerciseId: string) => {
    setGroups((gs) => gs.filter((g) => g.exercise.id !== exerciseId || g.sets.length > 0));
  }, []);

  // ── Logging ───────────────────────────────────────────────────────────────────────────────
  const handleLog = useCallback(
    (exerciseId: string, draft: SetDraft) => {
      const clientId = crypto.randomUUID();
      const optimistic: LogSet = {
        clientId,
        serverId: null,
        setNumber: maxSetNumber(groups.find((g) => g.exercise.id === exerciseId)) + 1,
        weightKg: draft.weightKg,
        reps: draft.reps,
        holdSeconds: draft.holdSeconds,
        rpe: draft.rpe,
        status: "saving",
        isPr: false,
        prType: null,
        prValue: null,
        prUnit: null,
      };
      setGroups((gs) =>
        gs.map((g) => (g.exercise.id === exerciseId ? { ...g, sets: [...g.sets, optimistic] } : g)),
      );
      setRestKey((k) => k + 1);
      setRestActive(true);
      void submit(exerciseId, optimistic);
    },
    [groups, submit],
  );

  const handleRetry = useCallback(
    (clientId: string) => {
      const group = groups.find((g) => g.sets.some((s) => s.clientId === clientId));
      const set = group?.sets.find((s) => s.clientId === clientId);
      if (!group || !set) return;
      patchSet(clientId, { status: "saving", errorMessage: undefined });
      void submit(group.exercise.id, { ...set, status: "saving" });
    },
    [groups, submit, patchSet],
  );

  const handleDeleteSet = useCallback(
    (clientId: string) => {
      const group = groups.find((g) => g.sets.some((s) => s.clientId === clientId));
      const set = group?.sets.find((s) => s.clientId === clientId);
      if (!group || !set) return;
      dropSet(clientId);
      // Purge any pending offline write so a deleted-while-queued set can't sync into an orphan.
      if (set.status === "queued") void removeQueuedSet(clientId);
      if (set.serverId) {
        apiDeleteSet(set.serverId).catch(() => {
          // Restore (in order) on failure so we never silently lose a persisted set.
          setGroups((gs) =>
            gs.map((g) =>
              g.exercise.id === group.exercise.id
                ? { ...g, sets: [...g.sets, set].sort((a, b) => a.setNumber - b.setNumber) }
                : g,
            ),
          );
        });
      }
    },
    [groups, dropSet],
  );

  // ── Deep-link: /log/[id]?add=<slug> pre-adds an exercise (from the Library "Log this") ────────
  const addParam = searchParams.get("add");
  const consumedAdd = useRef(false);
  useEffect(() => {
    if (!addParam || consumedAdd.current) return;
    consumedAdd.current = true;
    getExerciseBySlug(addParam)
      .then(addExercise)
      .catch(() => {
        /* unknown slug — ignore, just clean the URL */
      })
      .finally(() => router.replace(pathname, { scroll: false }));
  }, [addParam, addExercise, router, pathname]);

  const addedIds = new Set(groups.map((g) => g.exercise.id));
  const hasExercises = groups.length > 0;

  return (
    <div className={styles.logger}>
      <header className={styles.header}>
        <div>
          <p className="eyebrow">
            <LocalTime iso={session.performed_at} format="relative" />
          </p>
          <h1 className={styles.title}>{session.title ?? "Workout"}</h1>
          <p className={styles.sub}>
            Started <LocalTime iso={session.performed_at} format="time" />
            {session.type ? ` · ${session.type}` : ""}
          </p>
        </div>
        <SyncStatus online={online} pending={pending} />
      </header>

      {hasExercises ? (
        <div className={styles.blocks}>
          {groups.map((group) => (
            <FadeIn key={group.exercise.id}>
              <ExerciseBlock
                group={group}
                unitPref={unitPref}
                celebrateId={celebrateId}
                onLog={handleLog}
                onDeleteSet={handleDeleteSet}
                onRetrySet={handleRetry}
                onRemove={removeExercise}
              />
            </FadeIn>
          ))}
        </div>
      ) : (
        <div className={styles.empty}>
          <p className={styles.emptyTitle}>No exercises yet</p>
          <p className={styles.emptyText}>
            Add your first movement to start logging sets. The previous set pre-fills the next.
          </p>
        </div>
      )}

      <div className={styles.addBar}>
        <Button variant={hasExercises ? "outline" : "primary"} onClick={() => setPickerOpen(true)}>
          + Add exercise
        </Button>
      </div>

      <div className={styles.finishBar}>
        <FinishWorkout
          sessionId={session.id}
          endedAt={session.ended_at}
          durationMinutes={session.duration_minutes}
          pending={pending}
        />
      </div>

      <ExercisePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onAdd={(exercise) => {
          addExercise(exercise);
          setPickerOpen(false);
        }}
        addedIds={addedIds}
      />

      <RestTimer active={restActive} startKey={restKey} onDismiss={() => setRestActive(false)} />
    </div>
  );
}
