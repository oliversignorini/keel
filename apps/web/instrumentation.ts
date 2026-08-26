// Next.js instrumentation hook — Sentry, server + edge runtimes (PRD §4
// Integration points: "Both runtimes, releases tied to git SHA, source
// maps uploaded"; docs/plans/phase-8.md 8.4).
//
// @sentry/nextjs 8.x requires Sentry.init() to run from here (a runtime
// warning otherwise) rather than the legacy sentry.server.config.ts /
// sentry.edge.config.ts files. sentry.client.config.ts is unrelated —
// the browser runtime still uses that file.
//
// No DSN exists for this project yet — Sentry.init() with a blank dsn
// is a documented no-op (same treatment as keel/core/sentry.py on the
// backend), so this file is always safe to load.
export async function register() {
  const Sentry = await import("@sentry/nextjs");

  const options = {
    dsn: process.env.SENTRY_DSN ?? process.env.NEXT_PUBLIC_SENTRY_DSN,
    environment: process.env.SENTRY_ENVIRONMENT ?? "development",
    // Same source as the backend's SENTRY_RELEASE (config/settings/
    // base.py) and sentry.client.config.ts's browser-side release.
    release:
      process.env.NEXT_PUBLIC_SENTRY_RELEASE ??
      process.env.RAILWAY_GIT_COMMIT_SHA ??
      process.env.GIT_SHA ??
      "dev",
    tracesSampleRate: 0,
  };

  // middleware.ts (Edge) and server components/route handlers (Node)
  // both funnel through this one register() — a runtime check picks
  // the right init rather than needing two entry points.
  if (process.env.NEXT_RUNTIME === "nodejs" || process.env.NEXT_RUNTIME === "edge") {
    Sentry.init(options);
  }
}
