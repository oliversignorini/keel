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

async function latestMessageTo(request: import("@playwright/test").APIRequestContext, email: string) {
  const response = await request.get(`${MAILPIT_API}/search`, { params: { query: `to:${email}` } });
  const body = await response.json();
  return body.messages?.[0];
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

  const detail = await (
    await request.get(`${MAILPIT_API}/message/${message.ID}`)
  ).json();
  const link = /https?:\/\/[^\s"]+\/verify-email\/[A-Za-z0-9_-]+/.exec(detail.Text ?? detail.HTML ?? "")?.[0];
  expect(link, "email body should contain a /verify-email/[key] link").toBeTruthy();

  await page.goto(new URL(link!).pathname);
  await expect(page).toHaveURL(/\/onboarding/);
});

test("login with valid credentials establishes a session and logout ends it", async ({ page, request }) => {
  const email = uniqueEmail();
  const password = "correct horse battery staple 1";

  // Seed the account directly against the API so this test is independent
  // of the signup test above.
  await request.post("http://localhost:8000/_allauth/browser/v1/auth/signup", {
    data: { email, password },
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /log in/i }).click();

  await expect(page).toHaveURL(/\/app/);

  const sessionCookie = (await page.context().cookies()).find((cookie) => cookie.name === "sessionid");
  expect(sessionCookie, "a session cookie should be set after login").toBeTruthy();
  expect(sessionCookie?.httpOnly).toBe(true);
  expect(sessionCookie?.sameSite).toBe("Lax");
});

test("password reset round-trips end to end via Mailpit", async ({ page, request }) => {
  const email = uniqueEmail();
  const password = "correct horse battery staple 1";
  const newPassword = "correct horse battery staple 2";

  await request.post("http://localhost:8000/_allauth/browser/v1/auth/signup", {
    data: { email, password },
  });

  await page.goto("/reset-password");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: /send reset link/i }).click();
  await expect(page.getByRole("status")).toContainText(/reset link/i);

  const message = await latestMessageTo(request, email);
  expect(message).toBeTruthy();
  const detail = await (
    await request.get(`${MAILPIT_API}/message/${message.ID}`)
  ).json();
  const link = /https?:\/\/[^\s"]+\/reset-password\/[A-Za-z0-9_-]+/.exec(detail.Text ?? detail.HTML ?? "")?.[0];
  expect(link).toBeTruthy();

  await page.goto(new URL(link!).pathname);
  await page.getByLabel("New password").fill(newPassword);
  await page.getByRole("button", { name: /set new password/i }).click();
  await expect(page).toHaveURL(/\/app/);
});
