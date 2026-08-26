// Sentry, browser runtime (PRD §4 Integration points: "Both runtimes,
// releases tied to git SHA, source maps uploaded"; docs/plans/phase-8.md
// 8.4). No DSN exists for this project yet — Sentry.init() with a blank
// dsn is a documented no-op (same treatment as keel/core/sentry.py on
// the backend), so this file is always safe to load. See
// NEXT_PUBLIC_SENTRY_RELEASE below for how the release is set without a
// build-time secret.
import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? "development",
  // Set at build time from the same git SHA the backend release uses
  // (RAILWAY_GIT_COMMIT_SHA / GIT_SHA — see next.config.ts's `env` block
  // and .env.example) — NEXT_PUBLIC_ vars are inlined at build time, so
  // this can't read process.env.GIT_SHA directly at runtime in the
  // browser.
  release: process.env.NEXT_PUBLIC_SENTRY_RELEASE,
  tracesSampleRate: 0,
  // No session replay / performance product opted into by default — a
  // template default should not enable capture surfaces a project
  // hasn't decided it wants (same reasoning as send_default_pii=False
  // on the backend).
  replaysSessionSampleRate: 0,
  replaysOnErrorSampleRate: 0,
});
