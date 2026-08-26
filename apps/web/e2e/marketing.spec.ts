import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * The (marketing) route group's own Playwright specs — kept separate from
 * e2e/accessibility.spec.ts (auth/account routes) so `init` can delete
 * this one file when the marketing site is declined (PRD §8 Phase 9; see
 * docs/marketing-removal.md).
 */
const MARKETING_ROUTES = [
  "/",
  "/pricing",
  "/blog",
  "/blog/why-organisations-not-just-users",
  "/legal/terms",
  "/legal/privacy",
];

for (const route of MARKETING_ROUTES) {
  test(`axe: ${route} has zero violations`, async ({ page }) => {
    await page.goto(route);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });

  test(`${route} logs no browser console errors`, async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
    page.on("pageerror", (error) => errors.push(error.message));

    await page.goto(route);
    await page.waitForLoadState("networkidle");

    expect(errors).toEqual([]);
  });
}

test("sitemap.xml includes marketing and blog routes, excludes /app/*", async ({ request }) => {
  const response = await request.get("/sitemap.xml");
  const body = await response.text();

  expect(body).toContain("/pricing");
  expect(body).toContain("/blog/why-organisations-not-just-users");
  expect(body).not.toContain("/app/");
});

test("robots.txt disallows the authenticated app", async ({ request }) => {
  const response = await request.get("/robots.txt");
  const body = await response.text();

  expect(body).toContain("Disallow: /app/");
});

test("the apex host serves a favicon (docs/plans/phase-8.md 8.8)", async ({ request }) => {
  const response = await request.get("/favicon.ico");

  expect(response.status()).toBe(200);
});
