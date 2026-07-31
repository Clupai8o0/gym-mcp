/*
 * Tempo service worker (docs/07 §PWA/offline). Makes the app installable and keeps a usable shell
 * offline so set logging can continue; the offline write-queue itself lives in the app (IndexedDB,
 * `lib/offline`), independent of the SW.
 *
 * **It never caches an authenticated page.** Authed routes are server-rendered HTML containing the
 * signed-in user's data — name, records, the lot — and a cache outlives the session cookie. Caching
 * them per-URL (as v2 did) meant the next person on a shared device could go offline, open
 * /dashboard, and read the previous user's training. Only `/` and `/offline` — which render no user
 * data — are cached; an offline hit on anything else falls through to /offline. `lib/pwa`
 * additionally wipes every cache on sign-out, as defence in depth.
 *
 * It never touches the API origin: only same-origin GETs are handled. Static build assets are
 * stale-while-revalidate. Only successful, same-origin ("basic") responses are ever cached, so a
 * 5xx / redirect / opaque response can't poison the cache.
 */
const VERSION = "v3";
const CACHE = `tempo-shell-${VERSION}`;
const OFFLINE_URL = "/offline";

// The only routes whose HTML is safe to keep: no session, no user data, no personalization.
const PUBLIC_PATHS = new Set(["/", OFFLINE_URL]);

const cacheable = (response) => response && response.ok && response.type === "basic";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      // Individually, so one unreachable page can't fail the whole install.
      Promise.allSettled([...PUBLIC_PATHS].map((path) => cache.add(path))),
    ),
  );
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

// Sign-out asks for a full wipe (see `lib/pwa.clearAppCaches`), belt-and-braces with the page's
// own `caches.delete` calls in case the page is closed before they resolve.
self.addEventListener("message", (event) => {
  if (event.data === "tempo:clear-caches") {
    event.waitUntil(caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k)))));
  }
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin GETs; API calls (cross-origin) pass straight through.
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    const isPublic = PUBLIC_PATHS.has(url.pathname);
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Authed HTML is read from the network and then forgotten — never written to a cache.
          if (isPublic && cacheable(response)) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(async () => {
          const cache = await caches.open(CACHE);
          const cached = isPublic ? await cache.match(request) : undefined;
          return cached ?? (await cache.match(OFFLINE_URL)) ?? Response.error();
        }),
    );
    return;
  }

  // Immutable build assets + icons: stale-while-revalidate. No user data by construction.
  if (
    url.pathname.startsWith("/_next/static/") ||
    /\.(?:svg|png|ico|webmanifest)$/.test(url.pathname)
  ) {
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
