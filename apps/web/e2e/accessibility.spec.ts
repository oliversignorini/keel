import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * WCAG 2.1 AA is a floor for every auth and account route (PRD §5
 * Accessibility floor; B.5). The /account/* routes are reached with a fake
 * session cookie so middleware (lib/auth/route-guard.ts) lets the request
 * through without a real API — the page then renders its loading/empty
 * state, which is what gets checked here. None of this requires the Django
 * API to be running.
 */
const AUTH_ROUTES = [
  "/login",
  "/signup",
  "/verify-email",
  "/verify-email/some-key",
  "/reset-password",
  "/reset-password/some-key",
  "/mfa",
];

const ACCOUNT_ROUTES = ["/account/profile", "/account/security", "/account/sessions"];

for (const route of AUTH_ROUTES) {
  test(`axe: ${route} has zero violations`, async ({ page }) => {
    await page.goto(route);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(results.violations).toEqual([]);
  });
}

for (const route of ACCOUNT_ROUTES) {
  test(`axe: ${route} has zero violations`, async ({ page, context }) => {
    await context.addCookies([
      { name: "sessionid", value: "e2e-fake-session", url: "http://localhost:3100" },
    ]);
    await page.goto(route);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(results.violations).toEqual([]);
  });
}
