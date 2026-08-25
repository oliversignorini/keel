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
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3100",
    trace: "on-first-retry",
  },
  webServer: {
    command: "next dev -p 3100",
    url: "http://localhost:3100",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
