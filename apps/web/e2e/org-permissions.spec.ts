import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * The load-bearing proof phase-3.md Worktree C asks for: "`<Can>` hides
 * actions; removing it client-side still yields 403 from the API." A
 * client-side gate can only ever decide what renders — it cannot affect
 * what a network request does, so the only real way to prove enforcement
 * lives on the server is to skip the client entirely: call the API
 * directly, with a real session that has no `members.invite`, and show
 * the same 403 a bypassed `<Can>` would have hidden.
 *
 * Every call below goes through Playwright's `request` API context —
 * never `page` — precisely so no React code, and therefore no `<Can>`,
 * is in the loop at any point. Each context gets its own CSRF token,
 * fetched and attached exactly the way packages/api-client/src/http's
 * mutator/csrf modules do for a real browser session — this test proves
 * the server enforces the permission, not that CSRF can be skipped.
 */

const API = "http://localhost:8000";
const MAILPIT_API = "http://localhost:8025/api/v1";

function uniqueEmail(label: string): string {
  return `e2e-${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function latestMessageTo(request: APIRequestContext, email: string) {
  const response = await request.get(`${MAILPIT_API}/search`, { params: { query: `to:${email}` } });
  const body = await response.json();
  return body.messages?.[0];
}

async function csrfToken(request: APIRequestContext): Promise<string> {
  await request.get(`${API}/_allauth/browser/v1/config`);
  const state = await request.storageState();
  const cookie = state.cookies.find((c) => c.name === "csrftoken");
  expect(cookie, "config endpoint should set a csrftoken cookie").toBeTruthy();
  return cookie!.value;
}

async function unsafePost(request: APIRequestContext, url: string, data?: unknown) {
  return request.post(url, { data, headers: { "X-CSRFToken": await csrfToken(request) } });
}

async function signUpAndVerify(request: APIRequestContext, email: string, password: string) {
  const signupResponse = await unsafePost(request, `${API}/_allauth/browser/v1/auth/signup`, {
    email,
    password,
  });
  expect(signupResponse.status(), await signupResponse.text()).toBeLessThan(500);

  const message = await latestMessageTo(request, email);
  expect(message, `verification email for ${email} should be caught at Mailpit`).toBeTruthy();
  const detail = await (await request.get(`${MAILPIT_API}/message/${message.ID}`)).json();
  // The key segment is percent-encoded (allauth's key contains ":", e.g.
  // "OA%3A1wyuWc%3A…") — Next's [key] route param decodes it on the way
  // in (app/(auth)/verify-email/[key]/page.tsx), which this test has to
  // do manually since it never renders that page. `\S+` rather than a
  // narrower charset because the encoded key can contain "%" itself.
  const link = /https?:\/\/\S+\/verify-email\/(\S+)/.exec(detail.Text ?? detail.HTML ?? "");
  expect(link, "email body should contain a /verify-email/[key] link").toBeTruthy();
  const key = decodeURIComponent(link![1]!);

  const verifyResponse = await unsafePost(request, `${API}/_allauth/browser/v1/auth/email/verify`, {
    key,
  });
  // A 401 here is expected and correct: verifying clears the pending
  // verify_email flow but doesn't itself establish a session (see the
  // explicit login call below) — only a 5xx would mean the verify call
  // itself failed.
  expect(verifyResponse.status(), await verifyResponse.text()).toBeLessThan(500);

  // Verifying the email does not itself establish an authenticated
  // session under ACCOUNT_EMAIL_VERIFICATION="mandatory" (confirmed
  // against the live server — it clears the pending verify_email flow but
  // leaves the session anonymous) — log in explicitly, same as a real
  // user would after confirming their address.
  const loginResponse = await unsafePost(request, `${API}/_allauth/browser/v1/auth/login`, {
    email,
    password,
  });
  expect(loginResponse.ok(), await loginResponse.text()).toBe(true);
}

/**
 * `Invitation.token` is signed and never returned by any API response
 * (InvitationSerializer excludes it deliberately) — only the emailed link
 * carries it, and invitation emails aren't sent yet (Resend integration is
 * Phase 5). Reading it straight from the dev database is test-only
 * plumbing to drive the accept step; nothing under apps/api changes.
 */
function readInvitationTokenFromDb(email: string): string {
  const apiDir = path.resolve(__dirname, "../../api");
  const script = [
    "from keel.organizations.models import Invitation",
    `invitation = Invitation.objects.filter(email=${JSON.stringify(email)}).order_by("-created_at").first()`,
    "print(invitation.token if invitation else '')",
  ].join("\n");
  const output = execFileSync("uv", ["run", "python", "manage.py", "shell", "-c", script], {
    cwd: apiDir,
    encoding: "utf-8",
  });
  const token = output.trim().split("\n").pop() ?? "";
  expect(token, `invitation token for ${email} should exist in the dev database`).not.toBe("");
  return token;
}

test("a Member session gets 403 insufficient_role calling the API directly — <Can> never enters the picture", async ({
  playwright,
}) => {
  const ownerEmail = uniqueEmail("owner");
  const memberEmail = uniqueEmail("member");
  const password = "correct horse battery staple 1";

  const ownerContext = await playwright.request.newContext();
  const memberContext = await playwright.request.newContext();

  await signUpAndVerify(ownerContext, ownerEmail, password);
  await signUpAndVerify(memberContext, memberEmail, password);

  // Atomic org creation (phase-3.md acceptance) also seeds the three
  // preset roles — B.1's create_organization service.
  const createOrgResponse = await unsafePost(ownerContext, `${API}/api/v1/orgs/`, {
    name: `Permissions Test ${Date.now()}`,
  });
  expect(createOrgResponse.ok(), await createOrgResponse.text()).toBe(true);
  const org = await createOrgResponse.json();

  const rolesResponse = await ownerContext.get(`${API}/api/v1/orgs/${org.slug}/roles/`);
  const roles = (await rolesResponse.json()).results as { id: string; name: string }[];
  const memberRole = roles.find((role) => role.name === "Member");
  expect(memberRole, "the Member preset should exist on every organisation").toBeTruthy();

  const inviteResponse = await unsafePost(
    ownerContext,
    `${API}/api/v1/orgs/${org.slug}/invitations/`,
    { email: memberEmail, role_id: memberRole!.id },
  );
  expect(inviteResponse.ok(), await inviteResponse.text()).toBe(true);

  const token = readInvitationTokenFromDb(memberEmail);
  const acceptResponse = await unsafePost(memberContext, `${API}/api/v1/invite/${token}/`);
  expect(acceptResponse.ok(), await acceptResponse.text()).toBe(true);

  // The web app's settings/members page wraps its "Invite" button in
  // `<Can code={Perm.MEMBERS_INVITE}>` (app/(app)/app/[org]/settings/members/page.tsx)
  // — a Member never sees it rendered. This call skips that entirely and
  // hits the same endpoint the button would have called, with a session
  // that genuinely lacks the permission.
  const bypassedResponse = await unsafePost(
    memberContext,
    `${API}/api/v1/orgs/${org.slug}/invitations/`,
    { email: uniqueEmail("blocked"), role_id: memberRole!.id },
  );

  expect(bypassedResponse.status()).toBe(403);
  const body = await bypassedResponse.json();
  expect(body.error.code).toBe("insufficient_role");

  await ownerContext.dispose();
  await memberContext.dispose();
});
