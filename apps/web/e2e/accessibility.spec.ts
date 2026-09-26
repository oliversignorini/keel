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
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
}

for (const route of ACCOUNT_ROUTES) {
  test(`axe: ${route} has zero violations`, async ({ page, context, baseURL }) => {
    if (!baseURL) throw new Error("baseURL is not configured");
    await context.addCookies([
      {
        name: "sessionid",
        value: "e2e-fake-session",
        url: baseURL,
      },
    ]);
    await page.goto(route);
    await expect(page).toHaveURL(new RegExp(`${route}$`));
    await expect(page.getByRole("tablist")).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
}

/**
 * Every account page's content is focusable-content-bearing (forms, links),
 * so per the WAI-ARIA tabs pattern the tabpanel itself shouldn't be a tab
 * stop (WCAG 2.4.7 Focus Visible — a bare tabpanel wrapper has no visible
 * focus style, so if it became focusable it'd be an invisible stop).
 */
test("account tabs: tabpanel is not a keyboard tab stop", async ({ page, context, baseURL }) => {
  if (!baseURL) throw new Error("baseURL is not configured");
  await context.addCookies([
    {
      name: "sessionid",
      value: "e2e-fake-session",
      url: baseURL,
    },
  ]);
  await page.goto("/account/profile");
  await page.getByRole("tab", { name: "Profile" }).focus();
  await page.keyboard.press("Tab");
  const focusedRole = await page.evaluate(() => document.activeElement?.getAttribute("role"));
  expect(focusedRole).not.toBe("tabpanel");
});
