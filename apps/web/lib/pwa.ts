/**
 * PWA housekeeping the app performs on the way out (Phase 11D).
 *
 * The service worker already refuses to cache authenticated HTML, so nothing of the signed-in
 * user's should be in the Cache Storage to begin with. This is the second lock: a device that
 * upgraded from an older worker still holds whatever that one cached, and a shared phone is
 * exactly where that matters. Sign-out wipes the lot.
 */

/** Delete every Cache Storage entry for this origin. Safe to call anywhere; never throws. */
export async function clearAppCaches(): Promise<void> {
  try {
    if (typeof caches === "undefined") return;
    const keys = await caches.keys();
    await Promise.all(keys.map((key) => caches.delete(key)));
    // Ask the worker to sweep too, in case the page is torn down mid-flight.
    navigator.serviceWorker?.controller?.postMessage("tempo:clear-caches");
  } catch {
    // Storage denied (private mode, quota) — signing out still proceeds.
  }
}
