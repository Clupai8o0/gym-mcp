"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui";
import { listExercises, NetworkError, type ExerciseQuery } from "@/lib/client";
import type { ThemePreference } from "@/lib/theme";
import type { Exercise } from "@/lib/types";
import { ExerciseGrid } from "./ExerciseGrid";
import styles from "./InfiniteExerciseGrid.module.css";

/**
 * Start fetching this far before the sentinel reaches the viewport, so the next page has usually
 * landed by the time the reader gets there — roughly two rows of scrolling at a normal pace.
 */
const PREFETCH_MARGIN = "800px";

/** Cap what we keep for the back-button restore. Ten pages is far past any real browsing session. */
const MAX_RESTORED = 480;

const CACHE_PREFIX = "tempo:library:";

const NO_ITEMS: Exercise[] = [];

// ── The back-button restore ──────────────────────────────────────────────────────────────────
//
// Read through `useSyncExternalStore` with an explicit server snapshot, the same way `lib/hydration`
// reads the clock and the timezone: the server has no idea what this tab has browsed, so it renders
// the first page and only the *hydrated* client extends it. No `setState` in an effect (which the
// React-19 lint rules reject), and no mismatch for React to recover from.

const NEVER: () => () => void = () => () => {};

/** `getSnapshot` must return a stable reference across calls, so parse results are memoized by raw text. */
const parsed = new Map<string, { raw: string; items: Exercise[] }>();

function readRestored(key: string): Exercise[] {
  let raw: string | null = null;
  try {
    raw = sessionStorage.getItem(CACHE_PREFIX + key);
  } catch {
    // Private mode or a blocked store — browsing just starts from the first page.
    return NO_ITEMS;
  }
  if (!raw) return NO_ITEMS;

  const memo = parsed.get(key);
  if (memo && memo.raw === raw) return memo.items;

  let items: Exercise[] = NO_ITEMS;
  try {
    const value: unknown = JSON.parse(raw);
    if (Array.isArray(value)) items = value as Exercise[];
  } catch {
    // A stale shape from an older build.
  }
  parsed.set(key, { raw, items });
  return items;
}

function writeRestored(key: string, items: Exercise[]): void {
  try {
    sessionStorage.setItem(CACHE_PREFIX + key, JSON.stringify(items.slice(0, MAX_RESTORED)));
  } catch {
    // Over quota — the restore is an optimization, never a requirement.
  }
}

/** The run of pages this tab had scrolled through for these filters; empty until hydrated. */
function useRestored(key: string): Exercise[] {
  const snapshot = useCallback(() => readRestored(key), [key]);
  const server = useCallback(() => NO_ITEMS, []);
  return useSyncExternalStore(NEVER, snapshot, server);
}

/** Append `next` after `base`, dropping anything already present. Order is preserved. */
function appendNew(base: Exercise[], next: Exercise[]): Exercise[] {
  if (next.length === 0) return base;
  const seen = new Set(base.map((exercise) => exercise.id));
  const fresh = next.filter((exercise) => !seen.has(exercise.id));
  return fresh.length === 0 ? base : [...base, ...fresh];
}

export interface InfiniteExerciseGridProps {
  /** The first page, rendered on the server so the catalog is in the initial HTML. */
  initial: Exercise[];
  /** Total matching the active filters, per the server. */
  initialTotal: number;
  /** Window size for every subsequent request. */
  pageSize: number;
  /** The active catalog filters, without the window — offset is derived from what's loaded. */
  query: ExerciseQuery;
  /** Resolved server-side from the theme cookie so the first paint has the right linework. */
  preference: ThemePreference;
  /** Stable identity for the active filter set: resets state, and buckets the restore cache. */
  cacheKey: string;
}

/**
 * The catalog grid with scroll pagination.
 *
 * Each page after the first is fetched **straight from the browser to the API** (`lib/client`),
 * not through the Next.js function — one hop instead of two, and no server re-render of the page
 * around it. The first page still arrives server-rendered in the HTML, so the LCP tiles and their
 * illustrations are unaffected.
 *
 * An `IntersectionObserver` on a sentinel below the grid does the loading; the visible **Load
 * more** button is the same action, kept in the DOM so the list stays advanceable by keyboard and
 * recoverable when a request fails.
 *
 * What has been loaded is mirrored into `sessionStorage` per filter set, so tapping into an
 * exercise and coming back restores the run you had scrolled through instead of snapping back to
 * the first page.
 */
export function InfiniteExerciseGrid({
  initial,
  initialTotal,
  pageSize,
  query,
  preference,
  cacheKey,
}: InfiniteExerciseGridProps) {
  /** Pages fetched during *this* mount. The first page and the restored run are not state. */
  const [loaded, setLoaded] = useState<Exercise[]>(NO_ITEMS);
  /** The server's count, until a page response supersedes it. */
  const [fetchedTotal, setFetchedTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters changed: the server has already sent a fresh first page, so drop this mount's run
  // rather than appending to it. React's "adjust state when a prop changes" pattern — no effect,
  // no wasted render with stale tiles (the same idiom `FilterBar` uses for the search box).
  const [syncedKey, setSyncedKey] = useState(cacheKey);
  if (cacheKey !== syncedKey) {
    setSyncedKey(cacheKey);
    setLoaded(NO_ITEMS);
    setFetchedTotal(null);
    setError(null);
  }

  const restored = useRestored(cacheKey);
  const items = useMemo(
    () => appendNew(appendNew(initial, restored), loaded),
    [initial, restored, loaded],
  );
  // The server's total is the fresh one; a page response only supersedes it once we've asked again.
  const total = fetchedTotal ?? initialTotal;
  const hasMore = items.length < total;

  const count = items.length;
  const inFlight = useRef(false);

  const loadMore = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    setError(null);
    try {
      const page = await listExercises({ ...query, limit: pageSize, offset: count });
      if (page.items.length === 0) {
        // The catalog shifted under us; stop rather than spin on a fixed offset.
        setFetchedTotal(count);
      } else {
        setFetchedTotal(page.total);
        setLoaded((prev) => [...prev, ...page.items]);
      }
    } catch (cause) {
      setError(
        cause instanceof NetworkError
          ? "You appear to be offline. Check your connection and try again."
          : "Couldn't load more exercises.",
      );
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, [count, pageSize, query]);

  // Mirror the run out to sessionStorage so a round trip to a detail page can come back to it.
  // Syncing React state *to* an external system is what an effect is for.
  useEffect(() => {
    if (items.length <= initial.length) return;
    writeRestored(cacheKey, items);
  }, [cacheKey, items, initial.length]);

  // Auto-load as the sentinel approaches. Paused while a request is in flight or after a failure,
  // so a flaky connection surfaces the retry button instead of retrying on every scroll frame.
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !hasMore || error || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) void loadMore();
      },
      { rootMargin: PREFETCH_MARGIN },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, error, loadMore]);

  return (
    <>
      <p className={styles.count} aria-live="polite">
        Showing <span className="tnum">{count}</span> of <span className="tnum">{total}</span>
      </p>

      <ExerciseGrid exercises={items} preference={preference} pageSize={pageSize} />

      {hasMore && (
        <div className={styles.footer}>
          {/* Zero-height and outside the flow of meaning — purely the "we're near the end" trip
              wire. The button below it is the real, focusable control. */}
          <div ref={sentinelRef} className={styles.sentinel} aria-hidden />
          {error ? (
            <div className={styles.error} role="alert">
              <p className={styles.errorText}>{error}</p>
              <Button variant="outline" onClick={() => void loadMore()}>
                Try again
              </Button>
            </div>
          ) : (
            <Button variant="outline" loading={loading} onClick={() => void loadMore()}>
              Load more
            </Button>
          )}
        </div>
      )}
    </>
  );
}
