import type { MetadataRoute } from "next";
import { headers } from "next/headers";

import { SITE_URL } from "@/lib/site";
import { isAppHost } from "@/lib/host";

/** Disallows the authenticated app and account surfaces; everything under
 * the (marketing) group is indexable. Deleted along with
 * the rest of the marketing site by `init` — see docs/marketing-removal.md.
 *
 * Host-aware since the app moved onto its own subdomain:
 * `robots.txt` is served per-host, so a single static rule list no
 * longer covers both — the apex's `Disallow: /app/` never matched
 * anything on the app host to begin with, since the app host's visible
 * URLs dropped the /app segment (middleware.ts). The app host now gets
 * its own, blanket `Disallow: /` — every page behind it requires a
 * session, so there is nothing on it a crawler should ever index.
 */
export default async function robots(): Promise<MetadataRoute.Robots> {
  const host = (await headers()).get("host") ?? "";

  if (isAppHost(host)) {
    return {
      rules: { userAgent: "*", disallow: "/" },
      sitemap: `${SITE_URL}/sitemap.xml`,
    };
  }

  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/app/", "/account/", "/login", "/signup", "/onboarding", "/invite/"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
