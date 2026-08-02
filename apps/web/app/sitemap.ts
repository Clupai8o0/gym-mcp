import type { MetadataRoute } from "next";

import { BASE_URL } from "@/lib/env";

/**
 * The marketing page is the only publicly reachable route. Everything under `(app)` calls
 * `requireUser()` and redirects signed-out visitors to Google, so listing those URLs would put
 * a set of guaranteed redirects into the index and dilute the one page that can actually rank.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: `${BASE_URL}/`,
      changeFrequency: "monthly",
      priority: 1,
    },
  ];
}
