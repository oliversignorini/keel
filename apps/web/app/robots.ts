import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

/** Disallows the authenticated app and account surfaces; everything under
 * the (marketing) group is indexable (phase-7.md 7.5). Deleted along with
 * the rest of the marketing site by `init` — see docs/marketing-removal.md. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/app/", "/account/", "/login", "/signup", "/onboarding", "/invite/"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
