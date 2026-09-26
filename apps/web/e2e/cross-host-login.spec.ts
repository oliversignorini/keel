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
 * Requires the `seed_demo` fixture (owner@demo.keel.test /
 * demo-password-123, org "Demo Org" / demo-org — apps/api/keel/organizations/
 * management/commands/seed_demo.py). CI and `e2e:baseline` run this under
 * the default `playwright.config.ts` (its own webServer and global setup),
 * with `E2E_BASE_URL`/`E2E_LVH_BASE_URL` pointing at the lvh.me host.
 * `playwright.cross-host.config.ts` is only for driving an already-running
 * `pnpm dev` by hand.
 */
const APEX = process.env.E2E_LVH_BASE_URL ?? process.env.E2E_BASE_URL ?? "http://lvh.me:3000";
const APP = APEX.replace("//lvh.me", "//app.lvh.me");

// Serial, not parallel: both tests hit the app-host org route for the
// first time, and under CI's default fullyParallel concurrency they'd
// compile it at once. Combined with a cold `next dev` (a fresh server per
// CI step; playwright.config.ts's own comment puts a cold compile at
// ~40-60s on a CI runner), that race can blow the default 30s test
// timeout — test.slow() below triples the budget instead of relying on
// one test's compile warming the other.
test.describe.configure({ mode: "serial" });
test.slow();

test("logs in on the apex and lands authenticated on the app subdomain", async ({ page }) => {
  // Visiting the app host while signed out redirects to the apex login,
  // with an absolute next= that can send the browser back across hosts.
  await page.goto(`${APP}/demo-org`);
  await expect(page).toHaveURL((url) => url.href.startsWith(`${APEX}/login?next=`));

  await page.getByLabel("Email").fill("owner@demo.keel.test");
  await page.getByLabel("Password").fill("demo-password-123");
  await page.getByRole("button", { name: "Log in" }).click();

  // The redirect after login must cross back to the app host — this is
  // the one a client-side router.push cannot do, and the whole reason
  // navigateTo() (lib/navigation.ts) exists. Generous timeout: this is
  // the assertion that pays for /demo-org's first, cold compile.
  await expect(page).toHaveURL(`${APP}/demo-org`, { timeout: 60_000 });
  await expect(page.getByRole("heading", { name: "Demo Org" })).toBeVisible();

  // The session cookie set on the apex during login is genuinely being
  // sent to, and accepted by, the app subdomain — not just a client-side
  // redirect that happens to land on the right URL. The route is already
  // compiled by now, so the default timeout is enough.
  await page.reload();
  await expect(page).toHaveURL(`${APP}/demo-org`);
  await expect(page.getByRole("heading", { name: "Demo Org" })).toBeVisible();
});

test("unauthenticated access to the app subdomain redirects to the apex login with a working next=", async ({
  page,
}) => {
  await page.goto(`${APP}/demo-org/settings/general`);
  await expect(page).toHaveURL(
    `${APEX}/login?next=` + encodeURIComponent(`${APP}/demo-org/settings/general`),
  );

  await page.getByLabel("Email").fill("owner@demo.keel.test");
  await page.getByLabel("Password").fill("demo-password-123");
  await page.getByRole("button", { name: "Log in" }).click();

  // First hit on /demo-org/settings/general — same cold-compile risk as
  // the first test's post-login assertion above.
  await expect(page).toHaveURL(`${APP}/demo-org/settings/general`, { timeout: 60_000 });
});
