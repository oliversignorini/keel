import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext } from "@playwright/test";

/**
 * WCAG 2.1 AA is a floor for every auth and account route (PRD §5
 * Accessibility floor; B.5). The auth routes below need no session at all.
 * The /account/* routes are different: they're reached with a *real*
 * signed-in session (the seed_demo owner), because a fake sessionid cookie
 * 401s against the live Django API, and `useMe` (lib/org/use-me.ts, wired
 * into every account page via `ImpersonationBannerHost`) does a hard
 * `window.location.href` redirect to /login on any 401 — a real navigation
 * that races axe and either destroys its execution context mid-analysis or
 * silently makes the test axe-check the login page instead of the account
 * page. See findings/a11y/0001-account-tabs-invalid-aria.md.
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

const DEMO_OWNER_EMAIL = "owner@demo.keel.test";
const DEMO_OWNER_PASSWORD = "demo-password-123";

for (const route of AUTH_ROUTES) {
  test(`axe: ${route} has zero violations`, async ({ page }) => {
    await page.goto(route);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
}

test.describe("account routes (signed in)", () => {
  let ownerStorageState: Awaited<ReturnType<BrowserContext["storageState"]>>;

  test.beforeAll(async ({ browser }) => {
    const setupContext = await browser.newContext();
    const setupPage = await setupContext.newPage();
    await setupPage.goto("/login");
    await setupPage.getByLabel("Email").fill(DEMO_OWNER_EMAIL);
    await setupPage.getByLabel("Password").fill(DEMO_OWNER_PASSWORD);
    await setupPage.getByRole("button", { name: /log in/i }).click();
    await setupPage.waitForURL(/\/app/);
    ownerStorageState = await setupContext.storageState();
    await setupContext.close();
  });

  /**
   * Waits for the page to actually be the signed-in account page under
   * test, not the login redirect it can still race to: the URL, the tab
   * list, and every "Loading…" placeholder having resolved. Running axe
   * before this settles is exactly how the account-route checks used to
   * pass against the wrong page (see the file-level comment above).
   */
  async function expectAccountPageSettled(page: import("@playwright/test").Page, route: string) {
    await expect(page).toHaveURL(new RegExp(`${route}$`));
    await expect(page.getByRole("tablist")).toBeVisible();
    await expect(page.getByText("Loading…")).toHaveCount(0);
  }

  for (const route of ACCOUNT_ROUTES) {
    test(`axe: ${route} has zero violations`, async ({ browser }) => {
      const context = await browser.newContext({ storageState: ownerStorageState });
      const page = await context.newPage();
      await page.goto(route);
      await expectAccountPageSettled(page, route);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(results.violations).toEqual([]);
      await context.close();
    });
  }

  /**
   * Every account page's content is focusable-content-bearing (forms, links),
   * so per the WAI-ARIA tabs pattern the tabpanel itself shouldn't be a tab
   * stop (WCAG 2.4.7 Focus Visible — a bare tabpanel wrapper has no visible
   * focus style, so if it became focusable it'd be an invisible stop).
   */
  test("account tabs: tabpanel is not a keyboard tab stop", async ({ browser }) => {
    const context = await browser.newContext({ storageState: ownerStorageState });
    const page = await context.newPage();
    await page.goto("/account/profile");
    await expectAccountPageSettled(page, "/account/profile");
    await page.getByRole("tab", { name: "Profile" }).focus();
    await page.keyboard.press("Tab");
    const focusedRole = await page.evaluate(() => document.activeElement?.getAttribute("role"));
    expect(focusedRole).not.toBe("tabpanel");
    await context.close();
  });
});
