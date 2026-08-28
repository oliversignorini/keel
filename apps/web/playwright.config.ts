import { defineConfig, devices } from "@playwright/test";

/**
 * Signup/login/logout/reset (e2e/auth-flows.spec.ts) run against the real
 * Django API and Mailpit at localhost:8025 per B.5 — they require
 * p2-auth-api's allauth setup and will fail with connection/404 errors
 * until that worktree lands. axe-core checks (e2e/accessibility.spec.ts)
 * only need the Next.js pages to render and pass independently of the API.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: "list",
  // Same root cause as the webServer timeout below: a cold `next dev`
  // compile of each auth-flows.spec.ts route (a first-hit /login,
  // /signup, /app, ...) can itself run past the 5s default now that the
  // shadcn/radix dependency graph landed, so a `toHaveURL` assertion
  // right after a real navigation was timing out on the compile, not on
  // a broken redirect.
  expect: {
    timeout: 15_000,
  },
  // Runs one full signup/verify/reset round-trip before any test's clock
  // starts, so `next dev`'s per-route first-compile cost lands here
  // instead of inside whichever auth-flows.spec.ts test happens to run
  // first (see that file's global-setup.ts for why).
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3100",
    trace: "on-first-retry",
  },
  webServer: {
    command: "next dev -p 3100",
    url: "http://localhost:3100",
    reuseExistingServer: !process.env.CI,
    // 30s stopped being enough once the shadcn/radix dependency graph
    // landed (UX overhaul) — a cold `next dev` compile on a CI runner
    // now takes ~40-60s before the first byte.
    timeout: 120_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
