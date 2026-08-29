import { expect, test } from "@playwright/test";

/**
 * Cross-host login, driven in a real browser rather than reasoned about.
 * Session cookies spanning the apex and the app subdomain are the single
 * most likely thing to break, so this is exercised with Playwright rather
 * than argued about on paper:
 *
 *   Log in on the apex domain and land authenticated on the app
 *   subdomain.
 *
 * Requires a seeded user (e2e@example.com / s3cret-pass-1234, created
 * against the same dev database this ran against) and both dev servers
 * up on the lvh.me topology — see playwright.cross-host.config.ts.
 */
test("logs in on the apex and lands authenticated on the app subdomain", async ({ page }) => {
  // Visiting the app host while signed out redirects to the apex login,
  // with an absolute next= that can send the browser back across hosts.
  await page.goto("http://app.lvh.me:3000/e2e-org");
  await expect(page).toHaveURL(/^http:\/\/lvh\.me:3000\/login\?next=/);

  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("s3cret-pass-1234");
  await page.getByRole("button", { name: "Log in" }).click();

  // The redirect after login must cross back to the app host — this is
  // the one a client-side router.push cannot do, and the whole reason
  // navigateTo() (lib/navigation.ts) exists.
  await expect(page).toHaveURL("http://app.lvh.me:3000/e2e-org");
  await expect(page.getByRole("heading", { name: "E2E Org" })).toBeVisible();

  // The session cookie set on the apex during login is genuinely being
  // sent to, and accepted by, the app subdomain — not just a client-side
  // redirect that happens to land on the right URL.
  await page.reload();
  await expect(page).toHaveURL("http://app.lvh.me:3000/e2e-org");
  await expect(page.getByRole("heading", { name: "E2E Org" })).toBeVisible();
});

test("unauthenticated access to the app subdomain redirects to the apex login with a working next=", async ({
  page,
}) => {
  await page.goto("http://app.lvh.me:3000/e2e-org/settings/general");
  await expect(page).toHaveURL(
    "http://lvh.me:3000/login?next=" +
      encodeURIComponent("http://app.lvh.me:3000/e2e-org/settings/general"),
  );

  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("s3cret-pass-1234");
  await page.getByRole("button", { name: "Log in" }).click();

  await expect(page).toHaveURL("http://app.lvh.me:3000/e2e-org/settings/general");
});
