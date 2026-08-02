import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    // React `<ViewTransition>` for the Library list→detail shared-element morph (docs/08).
    viewTransition: true,
    /**
     * How long the client router may reuse an already-rendered segment.
     *
     * Every authenticated route here is fully dynamic (per-user data, `cache: "no-store"`), and
     * the default `dynamic: 0` throws that render away the instant you navigate off it — so
     * tapping an exercise and pressing Back re-runs the whole server render, and the fan-out of
     * API calls behind it, for a screen the user was looking at a second ago.
     *
     * 30s is short enough that a workout logged in another tab still shows up on the next visit,
     * and long enough that in-session Back/Forward is instant.
     *
     * The cost of turning this on is that a mutation is no longer guaranteed to be visible on the
     * *next* route you open, so every write whose result another route renders now busts the cache
     * explicitly with `router.refresh()`: `SessionStarter` (home + `/log` show the workout in
     * progress), `FinishWorkout`, `SkillsBoard` (home's "Top skill"), `ConnectionsList`,
     * `UnitToggle` and `ThemeToggle`. Writes that only feed their own screen — logging a set,
     * which `SessionLogger` holds in local state — need nothing.
     */
    staleTimes: { dynamic: 30 },
  },
  images: {
    // Catalog illustrations live on Vercel Blob (docs/06). Restrict to that host.
    remotePatterns: [
      {
        protocol: "https",
        hostname: "*.public.blob.vercel-storage.com",
        pathname: "/**",
      },
    ],
    // Monochrome line-art compresses dramatically better as AVIF → smaller LCP bytes.
    formats: ["image/avif", "image/webp"],
    // Catalog art is immutable per slug — cache the optimized variants for a year.
    minimumCacheTTL: 31536000,
    // Illustrations render small (card ≤240px, detail ≤480px CSS → ≤960px @2x); drop the
    // multi-thousand-px variants so we never generate/cache oversized srcset entries.
    deviceSizes: [480, 640, 828, 1080, 1200],
    imageSizes: [64, 96, 128, 240, 384],
  },
  async headers() {
    return [
      {
        // Never HTTP-cache the service worker, so updates ship on the next visit.
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
    ];
  },
};

export default nextConfig;
