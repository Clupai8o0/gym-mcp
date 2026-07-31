"use client";

/**
 * Two things the server genuinely cannot know: the viewer's timezone and the current time.
 *
 * Both are read through `useSyncExternalStore` with an explicit **server snapshot**, which is
 * the sanctioned way to render one thing during SSR and another after hydration — no
 * `setState` in an effect (which the React-19 lint rules reject, and which causes a cascading
 * render), and no mismatch React has to recover from.
 */
import { useSyncExternalStore } from "react";

const NEVER: () => () => void = () => () => {};

/** `false` during the server render and the hydration pass, `true` once the client owns the DOM. */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    NEVER,
    () => true,
    () => false,
  );
}

function subscribeToSeconds(onChange: () => void): () => void {
  const id = setInterval(onChange, 1000);
  return () => clearInterval(id);
}

// Second-resolution so consecutive `getSnapshot` calls inside one render return the same value
// (React requires a cached snapshot; a raw `Date.now()` would loop).
const secondsNow = (): number => Math.floor(Date.now() / 1000);
const noSeconds = (): number | null => null;

/** A clock that re-renders its consumer once a second; `null` until hydrated. */
export function useNowSeconds(): number | null {
  return useSyncExternalStore(subscribeToSeconds, secondsNow, noSeconds);
}
