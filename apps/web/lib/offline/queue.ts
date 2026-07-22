/**
 * Offline write-queue for set logging (docs/07 §PWA/offline). Logging must survive a flaky gym
 * connection: when a `log_set` write can't reach the API, it's persisted to IndexedDB keyed by a
 * stable client id (the same id the optimistic UI row carries), and flushed on reconnect. Scope is
 * deliberately narrow — only set writes queue; browsing/dashboard require connectivity.
 *
 * This module is storage only (no React, no network). `useOfflineQueue` drives it; `lib/client`
 * performs the actual POST during a flush.
 */
import type { SetCreate } from "../types";

const DB_NAME = "tempo-offline";
const STORE = "pending-sets";
const DB_VERSION = 1;

export interface QueuedSet {
  /** Client id shared with the optimistic UI row, so a flush can reconcile it. */
  clientId: string;
  sessionId: string;
  payload: SetCreate;
  queuedAt: number;
}

/** IndexedDB is unavailable during SSR and in some private modes — callers degrade gracefully. */
function hasIndexedDb(): boolean {
  return typeof indexedDB !== "undefined";
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "clientId" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDb();
  try {
    return await new Promise<T>((resolve, reject) => {
      const store = db.transaction(STORE, mode).objectStore(STORE);
      const req = run(store);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  } finally {
    db.close();
  }
}

export async function enqueueSet(item: QueuedSet): Promise<void> {
  if (!hasIndexedDb()) return;
  await tx("readwrite", (store) => store.put(item));
}

export async function removeQueuedSet(clientId: string): Promise<void> {
  if (!hasIndexedDb()) return;
  await tx("readwrite", (store) => store.delete(clientId));
}

export async function listQueuedSets(): Promise<QueuedSet[]> {
  if (!hasIndexedDb()) return [];
  const all = await tx<QueuedSet[]>("readonly", (store) => store.getAll() as IDBRequest<QueuedSet[]>);
  // Oldest first — preserve logging order on sync.
  return all.sort((a, b) => a.queuedAt - b.queuedAt);
}

export async function countQueuedSets(): Promise<number> {
  if (!hasIndexedDb()) return 0;
  return tx<number>("readonly", (store) => store.count());
}
