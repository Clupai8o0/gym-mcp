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
  },
};

export default nextConfig;
