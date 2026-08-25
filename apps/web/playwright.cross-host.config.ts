import { defineConfig, devices } from "@playwright/test";

/**
 * Plan 6.A's acceptance is behavioural and cross-host, which the default
 * playwright.config.ts's single localhost:3100 webServer can't exercise
 * (CORS_ALLOWED_ORIGINS / CSRF_TRUSTED_ORIGINS / SESSION_COOKIE_DOMAIN
 * are all configured for the lvh.me:3000 / api.lvh.me:8000 topology in
 * .env — see .env.example). This config has no webServer: it drives
 * whatever is already running on that topology (`pnpm dev` in apps/web,
 * `manage.py runserver` in apps/api) rather than spinning up a second,
 * differently-hosted instance.
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: "cross-host-login.spec.ts",
  fullyParallel: false,
  reporter: "list",
  use: {
    baseURL: "http://lvh.me:3000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
