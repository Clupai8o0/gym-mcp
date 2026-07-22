/*
 * Tempo service worker (docs/07 §PWA/offline). Makes the app installable and keeps a usable shell
 * offline so set logging can continue; the offline write-queue itself lives in the app (IndexedDB,
 * `lib/offline`), independent of the SW, so authenticated data is never served stale from cache.
 *
 * It never touches the API origin: only same-origin GETs are handled. Navigations are network-first
 * with a per-URL cache and a dedicated `/offline` fallback; static build assets are
 * stale-while-revalidate. Only successful, same-origin ("basic") responses are ever cached, so a
 * 5xx / redirect / opaque response can't poison the cache.
 */
const VERSION = "v2";
const CACHE = `tempo-shell-${VERSION}`;
const OFFLINE_URL = "/offline";

const cacheable = (response) => response && response.ok && response.type === "basic";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.add(OFFLINE_URL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin GETs; API calls (cross-origin) pass straight through.
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  // Navigations: network-first. Cache each page under its own URL so an offline revisit renders the
  // right route; fall back to that cached page, then to the dedicated offline page.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (cacheable(response)) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(async () => {
          const cache = await caches.open(CACHE);
          return (await cache.match(request)) ?? (await cache.match(OFFLINE_URL)) ?? Response.error();
        }),
    );
    return;
  }

  // Immutable build assets + icons: stale-while-revalidate.
  if (url.pathname.startsWith("/_next/static/") || /\.(?:svg|png|ico|webmanifest)$/.test(url.pathname)) {
    event.respondWith(
      caches.open(CACHE).then(async (cache) => {
        const cached = await cache.match(request);
        const network = fetch(request)
          .then((response) => {
            if (cacheable(response)) cache.put(request, response.clone());
            return response;
          })
          .catch(() => cached);
        return cached ?? network;
      }),
    );
  }
});
