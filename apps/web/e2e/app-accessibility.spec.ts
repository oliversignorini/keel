import { expect, test } from "@playwright/test";

/**
 * `axe-core` on the authenticated app — not just the auth/marketing
 * routes earlier phases covered (docs/plans/phase-8.md 8.7: "not just
 * the auth ones Phase 2 covered — marketing, app, settings, widgets").
 * Zero violations, WCAG 2.1 AA as the floor.
 *
 * Also proves the production CSP failure mode named in the brief
 * ("connect-src must allow the API origin — fails in production only"):
 * a real fetch() from the app origin to the API origin, in a real
 * browser, with zero CSP console violations.
 *
 * Signs up, verifies, and creates its own organisation via the API
 * (same technique as org-permissions.spec.ts) rather than depending on
 * a pre-seeded fixture user, so this file is runnable standalone. Run
 * against the real lvh.me topology (playwright.cross-host.config.ts) —
 * these routes only exist behind app.<host> host-based routing
 * (middleware.ts), which the default single-host config can't reach.
 */

const APEX = process.env.E2E_LVH_BASE_URL ?? "http://lvh.me:3000";
const API = APEX.replace("lvh.me", "api.lvh.me").replace(/:\d+$/, ":8000");
const APP_HOST = APEX.replace("//lvh.me", "//app.lvh.me");
const MAILPIT_API = "http://localhost:8025/api/v1";

function uniqueEmail(label: string): string {
  return `e2e-axe-${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function csrfToken(request: import("@playwright/test").APIRequestContext) {
  await request.get(`${API}/_allauth/browser/v1/config`);
  const state = await request.storageState();
  const cookie = state.cookies.find((c) => c.name === "csrftoken");
  expect(cookie).toBeTruthy();
  return cookie!.value;
}

async function unsafePost(
  request: import("@playwright/test").APIRequestContext,
  url: string,
  data?: unknown,
) {
  return request.post(url, { data, headers: { "X-CSRFToken": await csrfToken(request) } });
}

async function signUpVerifyLoginAndCreateOrg(
  request: import("@playwright/test").APIRequestContext,
) {
  const email = uniqueEmail("owner");
  const password = "correct horse battery staple 1";

  await unsafePost(request, `${API}/_allauth/browser/v1/auth/signup`, { email, password });

  const searchResponse = await request.get(`${MAILPIT_API}/search`, {
    params: { query: `to:${email}` },
  });
  const messages = (await searchResponse.json()).messages;
  const message = messages?.[0];
  expect(message, `verification email for ${email} should be caught at Mailpit`).toBeTruthy();
  const detail = await (await request.get(`${MAILPIT_API}/message/${message.ID}`)).json();
  const link = /https?:\/\/\S+\/verify-email\/(\S+)/.exec(detail.Text ?? detail.HTML ?? "");
  expect(link).toBeTruthy();
  const key = decodeURIComponent(link![1]!);
  await unsafePost(request, `${API}/_allauth/browser/v1/auth/email/verify`, { key });
  await unsafePost(request, `${API}/_allauth/browser/v1/auth/login`, { email, password });

  const orgResponse = await unsafePost(request, `${API}/api/v1/organizations/`, {
    name: `Axe Test ${Date.now()}`,
  });
  expect(orgResponse.ok(), await orgResponse.text()).toBe(true);
  return await orgResponse.json();
}

test.describe("axe: authenticated app routes", () => {
  test("dashboard, widgets, and every settings tab have zero violations", async ({
    playwright,
    browser,
  }) => {
    const AxeBuilder = (await import("@axe-core/playwright")).default;
    const apiContext = await playwright.request.newContext();
    const org = await signUpVerifyLoginAndCreateOrg(apiContext);
    const cookies = (await apiContext.storageState()).cookies;

    const browserContext = await browser.newContext();
    await browserContext.addCookies(cookies);
    const page = await browserContext.newPage();

    const routes = [
      `/${org.slug}`,
      `/${org.slug}/widgets`,
      `/${org.slug}/settings/general`,
      `/${org.slug}/settings/members`,
      `/${org.slug}/settings/roles`,
      `/${org.slug}/settings/billing`,
      `/${org.slug}/settings/audit`,
    ];

    for (const route of routes) {
      await page.goto(`${APP_HOST}${route}`);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(
        results.violations,
        `${route}: ${JSON.stringify(results.violations, null, 2)}`,
      ).toEqual([]);
    }

    await browserContext.close();
    await apiContext.dispose();
  });

  test("a real cross-origin fetch from the app origin to the API origin succeeds with no CSP violation", async ({
    playwright,
    browser,
  }) => {
    const apiContext = await playwright.request.newContext();
    const org = await signUpVerifyLoginAndCreateOrg(apiContext);
    const cookies = (await apiContext.storageState()).cookies;

    const browserContext = await browser.newContext();
    await browserContext.addCookies(cookies);
    const page = await browserContext.newPage();

    const cspViolations: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error" && /content security policy/i.test(message.text())) {
        cspViolations.push(message.text());
      }
    });

    await page.goto(`${APP_HOST}/${org.slug}`, { waitUntil: "networkidle" });

    const result = await page.evaluate(
      async ({ apiBase }) => {
        try {
          const res = await fetch(`${apiBase}/api/v1/me/`, { credentials: "include" });
          return { ok: true, status: res.status };
        } catch (e) {
          return { ok: false, error: String(e) };
        }
      },
      { apiBase: API },
    );

    expect(result.ok, JSON.stringify(result)).toBe(true);
    expect(result.status).toBe(200);
    expect(cspViolations).toEqual([]);

    await browserContext.close();
    await apiContext.dispose();
  });

  test("the app host serves a favicon (docs/plans/phase-8.md 8.8)", async ({ request }) => {
    const response = await request.get(`${APP_HOST}/favicon.ico`);

    expect(response.status()).toBe(200);
  });
});
