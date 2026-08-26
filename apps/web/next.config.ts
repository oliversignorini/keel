import { withContentCollections } from "@content-collections/next";
import type { NextConfig } from "next";

import { buildContentSecurityPolicy } from "./lib/csp";

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
export default withContentCollections(nextConfig);
