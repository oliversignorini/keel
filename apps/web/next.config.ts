import path from "node:path";

import { withContentCollections } from "@content-collections/next";
import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

import { buildContentSecurityPolicy } from "./lib/csp";

// Release tied to the git SHA — same source as the backend's SENTRY_RELEASE
// (config/settings/base.py). NEXT_PUBLIC_ vars are inlined at build
// time, so this has to be set here rather than read at runtime in the
// browser bundle (sentry.client.config.ts).
process.env.NEXT_PUBLIC_SENTRY_RELEASE ??=
  process.env.RAILWAY_GIT_COMMIT_SHA || process.env.GIT_SHA || "dev";

const nextConfig: NextConfig = {
  // Traced, self-contained server bundle — what apps/web/Dockerfile's
  // runtime stage copies instead of the whole pnpm workspace install.
  // outputFileTracingRoot has to point at the monorepo root or the trace
  // stops at apps/web and misses the workspace packages below.
  output: "standalone",
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),

  // @keel/ui ships TSX source, no build step of its own (a plain internal
  // workspace package) — Next transpiles it as part of this app's build.
  transpilePackages: ["@keel/ui"],

  // docs/adr/0002-auth-bff-shape.md: Django's own APPEND_SLASH redirects
  // `/api/v1/me` -> `/api/v1/me/`, and the generated client already
  // requests the trailing-slash form — but Next.js's own framework-level
  // trailing-slash redirect (`trailingSlash: false`'s default behaviour)
  // strips it right back off *before* the `/api/v1/[...path]` route
  // handler ever runs, so the two redirects fight forever. This is
  // exactly what `skipTrailingSlashRedirect` exists for (Next's own docs
  // name "acting as a reverse proxy" as the use case). Verified live:
  // without it, `GET /api/v1/me/` 308s to `/api/v1/me`, which the proxy
  // forwards slash-less, which Django 301s back to `/api/v1/me/` — an
  // infinite loop.
  skipTrailingSlashRedirect: true,

  // Security headers.
  // HSTS only over HTTPS — a plain-HTTP dev server would otherwise pin
  // itself into HTTPS-only in the browser, which is exactly the kind of
  // header that "only fails in production" cuts both ways on. next dev
  // always serves HTTP, so this is equivalent to "production only" here.
  async headers() {
    const csp = buildContentSecurityPolicy({
      sentryDsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
      posthogHost: process.env.NEXT_PUBLIC_POSTHOG_HOST,
      dev: process.env.NODE_ENV !== "production",
    });
    const headers = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "same-origin" },
      { key: "Content-Security-Policy", value: csp },
    ];
    if (process.env.NODE_ENV === "production") {
      headers.push({
        key: "Strict-Transport-Security",
        value: "max-age=63072000; includeSubDomains; preload",
      });
    }
    return [{ source: "/:path*", headers }];
  },
};

// Wires apps/web/content-collections.ts into the Next.js build. Removing
// the marketing route group means dropping this wrapper too — see
// docs/marketing-removal.md.
//
// withContentCollections returns a config object with several of
// nextConfig's own keys silently absent rather than merged through —
// verified directly: `headers` and `skipTrailingSlashRedirect` are both
// `undefined` on its return value even when present on the object passed
// in. Whatever it does internally, it isn't a full-config passthrough, so
// those two are re-applied explicitly afterward rather than trusted to
// have survived.
const configWithContentCollections: NextConfig = {
  ...withContentCollections(nextConfig),
  headers: nextConfig.headers,
  skipTrailingSlashRedirect: nextConfig.skipTrailingSlashRedirect,
  // Same passthrough gap, found the same way: with these left to the
  // wrapper, `next build` silently emits no .next/standalone at all and
  // the container image has nothing to run.
  output: nextConfig.output,
  outputFileTracingRoot: nextConfig.outputFileTracingRoot,
};

// Source-map upload needs SENTRY_AUTH_TOKEN/SENTRY_ORG/SENTRY_PROJECT —
// none exist for this project (.env.example). withSentryConfig degrades
// gracefully without them: the build still succeeds, just without
// resolved stack frames in Sentry — it does not fail the build or
// require credentials to exist.
export default withSentryConfig(configWithContentCollections, {
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  silent: true,
  widenClientFileUpload: true,
  disableLogger: true,
});
