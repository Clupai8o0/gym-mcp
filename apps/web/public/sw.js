/*
 * Tempo service worker (docs/07 §PWA/offline). Deliberately minimal for Phase 7 — it makes the app
 * installable and keeps the shell available offline so set logging can continue; install polish
 * (precache lists, richer offline UX) is Phase 9. It never touches the API origin: the offline
 * write-queue for set logging lives in the app (IndexedDB, `lib/offline`), independent of the SW,
 * so authenticated data is never served stale from cache.
 */
const CACHE = "tempo-shell-v1";
const OFFLINE_URL = "/log";

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

  // Navigations: network-first, falling back to the cached shell when offline.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(OFFLINE_URL, copy));
          return response;
        })
        .catch(() => caches.match(OFFLINE_URL).then((cached) => cached ?? Response.error())),
    );
    return;
  }

  // Static build assets: stale-while-revalidate (immutable, safe to cache).
  if (url.pathname.startsWith("/_next/static/") || url.pathname === "/icon.svg") {
    event.respondWith(
      caches.open(CACHE).then(async (cache) => {
        const cached = await cache.match(request);
        const network = fetch(request)
          .then((response) => {
            cache.put(request, response.clone());
            return response;
          })
          .catch(() => cached);
        return cached ?? network;
      }),
    );
  }
});
