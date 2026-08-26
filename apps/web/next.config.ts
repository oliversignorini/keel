import { withContentCollections } from "@content-collections/next";
import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

import { buildContentSecurityPolicy } from "./lib/csp";

// Release tied to the git SHA (PRD §4 Integration points; docs/plans/
// phase-8.md 8.4) — same source as the backend's SENTRY_RELEASE
// (config/settings/base.py). NEXT_PUBLIC_ vars are inlined at build
// time, so this has to be set here rather than read at runtime in the
// browser bundle (sentry.client.config.ts).
process.env.NEXT_PUBLIC_SENTRY_RELEASE ??=
  process.env.RAILWAY_GIT_COMMIT_SHA || process.env.GIT_SHA || "dev";

const nextConfig: NextConfig = {
  // @keel/ui ships TSX source, no build step of its own (a plain internal
  // workspace package) — Next transpiles it as part of this app's build.
  transpilePackages: ["@keel/ui"],

  // Security headers (PRD §3 NFR "Security"; docs/plans/phase-8.md 8.6).
  // HSTS only over HTTPS — a plain-HTTP dev server would otherwise pin
  // itself into HTTPS-only in the browser, which is exactly the kind of
  // header that "only fails in production" cuts both ways on. next dev
  // always serves HTTP, so this is equivalent to "production only" here.
  async headers() {
    const csp = buildContentSecurityPolicy({
      apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL,
      apiStreamUrl: process.env.NEXT_PUBLIC_API_STREAM_URL,
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

// Wires apps/web/content-collections.ts into the Next.js build (phase-7.md
// 7.4). Removing the marketing route group (PRD §8 Phase 9) means dropping
// this wrapper too — see docs/marketing-removal.md.
const configWithContentCollections = withContentCollections(nextConfig);

// Source-map upload (PRD §4: "source maps uploaded"; docs/plans/
// phase-8.md 8.4) needs SENTRY_AUTH_TOKEN/SENTRY_ORG/SENTRY_PROJECT —
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
