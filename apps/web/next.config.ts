import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    // React `<ViewTransition>` for the Library list→detail shared-element morph (docs/08).
    viewTransition: true,
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
