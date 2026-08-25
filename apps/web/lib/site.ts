/** The canonical origin the marketing site is served from — used by the
 * sitemap, JSON-LD, and Open Graph metadata, all of which need an
 * absolute URL rather than a path. Defaults to local dev; every real
 * deployment sets NEXT_PUBLIC_SITE_URL (see .env.example). */
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000").replace(
  /\/$/,
  "",
);
