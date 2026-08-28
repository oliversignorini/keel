import { chromium, request as playwrightRequest, type FullConfig } from "@playwright/test";

/**
 * `next dev` compiles each route on first request, not at server boot —
 * the 120s webServer timeout above only covers the first byte of `/`.
 * auth-flows.spec.ts's tests share one dev server (webServer.reuseExistingServer
 * is false in CI, so every `playwright test` invocation gets a cold one),
 * and whichever test runs first pays the compile cost of every auth route
 * it's the first to touch — signup, verify-email, verify-email/[key],
 * onboarding, login, app, reset-password, reset-password/[key] — inside
 * its own 30s test timeout. On a CI runner slow enough, that one test
 * times out even though nothing in the flow is actually broken.
 *
 * This warms every route those tests touch, through a real signup +
 * verify + reset round-trip, before any test's clock starts, so the
 * compile cost is paid once here instead of unluckily inside whichever
 * test happens to run first. Best-effort: a failure here just means the
 * warmup didn't help, not that the suite should abort before it starts.
 */

const MAILPIT_API = "http://localhost:8025/api/v1";

function uniqueEmail(label: string): string {
  return `e2e-warmup-${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function latestMessageTo(
  request: Awaited<ReturnType<typeof playwrightRequest.newContext>>,
  email: string,
) {
  const response = await request.get(`${MAILPIT_API}/search`, { params: { query: `to:${email}` } });
  const body = await response.json();
  return body.messages?.[0];
}

function extractKeyFromEmail(
  body: string,
  routeSegment: "verify-email" | "reset-password",
): string | null {
  const match = new RegExp(`https?://\\S+/${routeSegment}/(\\S+)`).exec(body);
  return match ? decodeURIComponent(match[1]!) : null;
}

export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0]?.use?.baseURL ?? "http://localhost:3100";
  const requestContext = await playwrightRequest.newContext();
  const browser = await chromium.launch();
  const page = await browser.newPage({ baseURL });
  page.setDefaultTimeout(60_000);
  page.setDefaultNavigationTimeout(60_000);

  try {
    const password = "correct horse battery staple 1";

    const verifyEmail = uniqueEmail("verify");
    await page.goto("/signup");
    await page.getByLabel("Email").fill(verifyEmail);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: /sign up/i }).click();
    await page.waitForURL(/\/verify-email$/);

    const verifyMessage = await latestMessageTo(requestContext, verifyEmail);
    const verifyKey = verifyMessage
      ? extractKeyFromEmail(
          (await (await requestContext.get(`${MAILPIT_API}/message/${verifyMessage.ID}`)).json())
            .Text ?? "",
          "verify-email",
        )
      : null;
    if (verifyKey) {
      await page.goto(`/verify-email/${encodeURIComponent(verifyKey)}`);
      await page.waitForURL(/\/onboarding/);
    }

    await page.goto("/login");
    await page.goto("/app");

    const resetEmail = uniqueEmail("reset");
    await page.goto("/signup");
    await page.getByLabel("Email").fill(resetEmail);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: /sign up/i }).click();
    await page.waitForURL(/\/verify-email$/);

    await page.goto("/reset-password");
    await page.getByLabel("Email").fill(resetEmail);
    await page.getByRole("button", { name: /send reset link/i }).click();

    const resetMessage = await latestMessageTo(requestContext, resetEmail);
    const resetKey = resetMessage
      ? extractKeyFromEmail(
          (await (await requestContext.get(`${MAILPIT_API}/message/${resetMessage.ID}`)).json())
            .Text ?? "",
          "reset-password",
        )
      : null;
    if (resetKey) {
      await page.goto(`/reset-password/${encodeURIComponent(resetKey)}`);
    }
  } catch {
    // Best-effort cache warm — a broken warmup run just forfeits the
    // benefit, it must never fail the suite before the real tests run.
  } finally {
    await page.close().catch(() => {});
    await browser.close().catch(() => {});
    await requestContext.dispose().catch(() => {});
  }
}
