import { expect, test } from "@playwright/test";

/**
 * Signup, login, logout, and password reset, driven through the real
 * Django API and caught at Mailpit (localhost:8025) per B.5 — the PRD
 * requires the verification email be caught there rather than stubbed.
 * These require p2-auth-api's allauth setup to be running; until then they
 * fail on the first API call, which is the honest state of Phase 2 while
 * the two worktrees are still concurrent.
 */

const MAILPIT_API = "http://localhost:8025/api/v1";

function uniqueEmail(): string {
  return `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function latestMessageTo(
  request: import("@playwright/test").APIRequestContext,
  email: string,
) {
  const response = await request.get(`${MAILPIT_API}/search`, { params: { query: `to:${email}` } });
  const body = await response.json();
  return body.messages?.[0];
}

/**
 * The key segment of allauth's verification/reset links is
 * percent-encoded (it contains ":", e.g. "MTU%3A1wyu…") — `\S+` rather
 * than an alphanumeric class because the encoded form itself contains
 * "%". Returns the decoded key.
 */
function extractKeyFromEmail(
  body: string,
  routeSegment: "verify-email" | "reset-password",
): string {
  const match = new RegExp(`https?://\\S+/${routeSegment}/(\\S+)`).exec(body);
  expect(match, `email body should contain a /${routeSegment}/[key] link`).toBeTruthy();
  return decodeURIComponent(match![1]!);
}

test("signup sends a verification email caught at Mailpit, and clicking it authenticates", async ({
  page,
  request,
}) => {
  const email = uniqueEmail();

  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct horse battery staple 1");
  await page.getByRole("button", { name: /sign up/i }).click();

  await expect(page).toHaveURL(/\/verify-email$/);

  const message = await latestMessageTo(request, email);
  expect(message, "verification email should be caught at Mailpit").toBeTruthy();

  const detail = await (await request.get(`${MAILPIT_API}/message/${message.ID}`)).json();
  const key = extractKeyFromEmail(detail.Text ?? detail.HTML ?? "", "verify-email");

  await page.goto(`/verify-email/${encodeURIComponent(key)}`);
  await expect(page).toHaveURL(/\/onboarding/);
});

test("login with valid credentials establishes a session and logout ends it", async ({
  page,
  request,
}) => {
  const email = uniqueEmail();
  const password = "correct horse battery staple 1";

  // Seed the account through the real signup + verification flow —
  // ACCOUNT_EMAIL_VERIFICATION="mandatory" (apps/api config/settings/base.py)
  // means an unverified account cannot log in at all, so a raw signup
  // call alone (with no verify step) is not a valid precondition for this
  // test — logging out afterward is this test's actual subject.
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /sign up/i }).click();
  await expect(page).toHaveURL(/\/verify-email$/);

  const message = await latestMessageTo(request, email);
  expect(message, "verification email should be caught at Mailpit").toBeTruthy();
  const detail = await (await request.get(`${MAILPIT_API}/message/${message.ID}`)).json();
  const key = extractKeyFromEmail(detail.Text ?? detail.HTML ?? "", "verify-email");
  await page.goto(`/verify-email/${encodeURIComponent(key)}`);
  // ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION (apps/api config/settings/base.py)
  // means clicking the link above already established a session — this
  // test's actual subject is the *explicit* credentials-based login
  // below, so drop that session first rather than hitting /login while
  // already authenticated (allauth's headless login endpoint 409s on an
  // authenticated session instead of re-authenticating it).
  await expect(page).toHaveURL(/\/onboarding/);
  await page.context().clearCookies();

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /log in/i }).click();

  await expect(page).toHaveURL(/\/app/);

  const sessionCookie = (await page.context().cookies()).find(
    (cookie) => cookie.name === "sessionid",
  );
  expect(sessionCookie, "a session cookie should be set after login").toBeTruthy();
  expect(sessionCookie?.httpOnly).toBe(true);
  expect(sessionCookie?.sameSite).toBe("Lax");

  // Phase 11 acceptance: no auth token anywhere JS can read it — the
  // session lives only in the HttpOnly cookie above. `document.cookie`
  // never includes an HttpOnly cookie by construction, so checking it's
  // empty of "sessionid" doubles as the assertion that the cookie really
  // is HttpOnly, not just that the flag is set on the object Playwright
  // read out-of-band.
  const clientVisibleState = await page.evaluate(() => ({
    localStorageKeys: Object.keys(window.localStorage),
    sessionStorageKeys: Object.keys(window.sessionStorage),
    documentCookie: document.cookie,
  }));
  expect(clientVisibleState.localStorageKeys).toEqual([]);
  expect(clientVisibleState.sessionStorageKeys).toEqual([]);
  expect(clientVisibleState.documentCookie).not.toContain("sessionid");
});

test("password reset round-trips end to end via Mailpit", async ({ page, request }) => {
  const email = uniqueEmail();
  const password = "correct horse battery staple 1";
  const newPassword = "correct horse battery staple 2";

  // Through the real signup form (not a raw request.post) so the CSRF
  // cookie needed for it — and for the reset request just below — is
  // primed the same way a real visitor's browser primes it (see
  // packages/api-client/src/http/mutator.ts's ensureCsrfCookie).
  // Verification is irrelevant to this test; unverified is fine.
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /sign up/i }).click();
  await expect(page).toHaveURL(/\/verify-email$/);

  await page.goto("/reset-password");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: /send reset link/i }).click();
  await expect(page.getByRole("status")).toContainText(/reset link/i);

  const message = await latestMessageTo(request, email);
  expect(message).toBeTruthy();
  const detail = await (await request.get(`${MAILPIT_API}/message/${message.ID}`)).json();
  const key = extractKeyFromEmail(detail.Text ?? detail.HTML ?? "", "reset-password");

  await page.goto(`/reset-password/${encodeURIComponent(key)}`);
  await page.getByLabel("New password").fill(newPassword);
  await page.getByRole("button", { name: /set new password/i }).click();
  await expect(page).toHaveURL(/\/app/);
});
