import type { MetadataRoute } from "next";

import { BASE_URL } from "@/lib/env";

/**
 * Authenticated routes are disallowed because a crawler reaching them gets a redirect to Google's
 * login, never content. Keeping them out of the crawl budget leaves it for the one page that has
 * something to index.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/dashboard", "/log", "/library", "/progress", "/settings", "/offline"],
    },
    sitemap: `${BASE_URL}/sitemap.xml`,
    host: BASE_URL,
  };
}
