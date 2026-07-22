"use client";

import { useEffect } from "react";

/**
 * Registers the app-shell service worker (docs/07 §PWA/offline) once, after load. Client-only and
 * render-nothing. The worker only enables install + offline shell; the set-logging offline queue is
 * app-managed (IndexedDB), so registration failing (e.g. unsupported browser) never breaks logging.
 */
export function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    // Register after load so it never contends with the initial render.
    const register = () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        /* SW unsupported / blocked — logging still works via the IndexedDB queue */
      });
    };
    if (document.readyState === "complete") register();
    else {
      window.addEventListener("load", register, { once: true });
      return () => window.removeEventListener("load", register);
    }
  }, []);

  return null;
}
