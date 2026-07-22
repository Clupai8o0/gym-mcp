"use client";

/**
 * React binding for the offline set-queue (docs/07 §PWA/offline). Tracks connectivity, exposes the
 * pending-write count, submits set logs (queuing them when the network is down), and flushes the
 * queue on reconnect — reconciling each synced write back into the UI via callbacks. Reconnect
 * flush is driven by the `online` event, which is reliable across browsers (unlike Background Sync).
 */
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { ClientApiError, NetworkError, logSet } from "../client";
import type { LoggedSet, SetCreate } from "../types";
import { countQueuedSets, enqueueSet, listQueuedSets, removeQueuedSet } from "./queue";

export interface SubmitSetArgs {
  clientId: string;
  sessionId: string;
  payload: SetCreate;
}

export type SubmitResult = { queued: false; result: LoggedSet } | { queued: true };

export interface UseOfflineQueueArgs {
  /** A queued write reached the server on reconnect — apply its authoritative result + PR verdict. */
  onSynced: (clientId: string, result: LoggedSet) => void;
  /** A queued write was permanently rejected (4xx) — drop the optimistic row + surface the error. */
  onSyncFailed: (clientId: string, error: ClientApiError) => void;
}

export interface OfflineQueue {
  online: boolean;
  pending: number;
  submitSet: (args: SubmitSetArgs) => Promise<SubmitResult>;
}

/** Subscribe to browser connectivity without an effect (SSR snapshot = online). */
function subscribeOnline(callback: () => void): () => void {
  window.addEventListener("online", callback);
  window.addEventListener("offline", callback);
  return () => {
    window.removeEventListener("online", callback);
    window.removeEventListener("offline", callback);
  };
}

export function useOfflineQueue({ onSynced, onSyncFailed }: UseOfflineQueueArgs): OfflineQueue {
  const online = useSyncExternalStore(
    subscribeOnline,
    () => navigator.onLine,
    () => true,
  );
  const [pending, setPending] = useState(0);

  const refreshPending = useCallback(async () => {
    setPending(await countQueuedSets());
  }, []);

  const flush = useCallback(async () => {
    const queued = await listQueuedSets();
    for (const item of queued) {
      try {
        const result = await logSet(item.sessionId, item.payload);
        await removeQueuedSet(item.clientId);
        onSynced(item.clientId, result);
      } catch (error) {
        if (error instanceof NetworkError) break; // still offline — retry on the next reconnect
        if (error instanceof ClientApiError) {
          await removeQueuedSet(item.clientId); // permanent failure — don't retry forever
          onSyncFailed(item.clientId, error);
          continue;
        }
        throw error;
      }
    }
    await refreshPending();
  }, [onSynced, onSyncFailed, refreshPending]);

  // Flush on reconnect (event callback) and once on mount (deferred a tick so the flush's async
  // setState never runs synchronously inside the effect body). Flush is idempotent per queued item.
  useEffect(() => {
    const onReconnect = () => void flush();
    window.addEventListener("online", onReconnect);
    const initial = setTimeout(() => {
      if (navigator.onLine) void flush();
      else void refreshPending();
    }, 0);
    return () => {
      clearTimeout(initial);
      window.removeEventListener("online", onReconnect);
    };
  }, [flush, refreshPending]);

  const submitSet = useCallback(
    async ({ clientId, sessionId, payload }: SubmitSetArgs): Promise<SubmitResult> => {
      const queue = async (): Promise<SubmitResult> => {
        await enqueueSet({ clientId, sessionId, payload, queuedAt: Date.now() });
        await refreshPending();
        return { queued: true };
      };
      if (!navigator.onLine) return queue();
      try {
        return { queued: false, result: await logSet(sessionId, payload) };
      } catch (error) {
        if (error instanceof NetworkError) return queue();
        throw error; // ClientApiError (validation, 409, …) → the caller handles it inline
      }
    },
    [refreshPending],
  );

  return { online, pending, submitSet };
}
