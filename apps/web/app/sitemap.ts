import type { MetadataRoute } from "next";

import { allPosts } from "content-collections";
import { SITE_URL } from "@/lib/site";

/** Marketing and blog routes only — `/app/*` is authenticated and must
 * not be indexed (phase-7.md 7.5; PRD §8 Phase 7 acceptance). Deleted
 * along with the rest of the marketing site by `init` — see
 * docs/marketing-removal.md. */
export default function sitemap(): MetadataRoute.Sitemap {
  const staticRoutes = ["/", "/pricing", "/blog", "/legal/terms", "/legal/privacy"].map((path) => ({
    url: `${SITE_URL}${path}`,
    lastModified: new Date(),
  }));

  const postRoutes = allPosts.map((post) => ({
    url: `${SITE_URL}/blog/${post.slug}`,
    lastModified: new Date(post.date),
  }));

  return [...staticRoutes, ...postRoutes];
}
