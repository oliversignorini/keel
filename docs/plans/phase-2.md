# Phase 2 — Authentication

**Source of truth:** `keel-prd.md` v1.2 — §4 "Auth architecture", §5 Routes, §6 "Signup → first organisation → subscription" and "Permission denial", §7 identity endpoints, §8 Phase 2.
**Depends on:** Phase 1, complete and verified.
**Size:** Large. Split across two worktrees that run concurrently.

---

## Two worktrees

| Worktree | Owns | Branch |
|---|---|---|
| **`p2-auth-api`** | Everything under `apps/api` — allauth configuration, cookies, CORS/CSRF, settings, the merged OpenAPI spec, backend tests | `phase-2-auth-api` |
| **`p2-auth-web`** | Everything under `apps/web` and `packages/api-client` — auth pages, middleware guards, the generated client, Playwright | `phase-2-auth-web` |

They are concurrent because allauth's endpoint surface is **already specified** — it is allauth's own OpenAPI document, not something the API worktree invents. The web worktree can build against `/_allauth/browser/v1/...` from the PRD's §7 endpoint list on day one and regenerate the client the moment the API worktree lands.

**Neither worktree writes migrations.** Phase 1 landed the schema. `User` already exists. If you believe you need a migration, you have found either a Phase 1 gap or a scope error — report it, do not generate one.

**Neither worktree touches `keel/organizations`, `keel/billing`, or any permission code.** Phase 3 owns those. Signup ends at a session; what happens next — organisation creation, the `/onboarding` route — is Phase 3's.

---

# Worktree A — `p2-auth-api`

### A.1 — allauth headless

- `django-allauth` 65.19+ with `[headless-spec, mfa, socialaccount]`. `HEADLESS_ONLY = True`.
- Email/password signup, email verification, password reset.
- Google as the one configured social provider. Others are a settings addition, not a code change — make sure that is true, and say so in the report.
- `allauth.usersessions` for listing and revoking active sessions.
- MFA (TOTP) **scaffolded and disabled behind a settings flag**, per the PRD. WebAuthn is available in allauth but is not in Phase 2 scope; leave it off and note the flag that turns it on.
- allauth's built-in rate limiting configured, not left at defaults you have not read.
- `HEADLESS_FRONTEND_URLS` pointed at the Next routes: `/verify-email/[key]`, `/reset-password/[key]`, `/invite/[token]`.

### A.2 — Cookies, CORS, CSRF

This is the part that silently breaks in production and is the PRD's first named risk. Get it right and test it.

- `SESSION_COOKIE_*`: HttpOnly, Secure, `SameSite=Lax`, `Domain` set to the **registrable** domain (`.acme.com`) so `acme.com` and `api.acme.com` share it.
- `CSRF_TRUSTED_ORIGINS` and `CSRF_COOKIE_*` configured to match.
- CORS with `allow_credentials` and an explicit origin list. **No wildcard** — credentialed CORS forbids it and the browser error does not say so clearly.
- A **startup check** that fails loudly when `SESSION_COOKIE_DOMAIN` is not a parent of the configured app domain. PRD §10 names this as the mitigation for the risk; implement it as a Django system check so it fires on `manage.py check`, not at first request.
- Document the Vercel preview-domain constraint (`*.preview.acme.com`, requires Vercel Pro) in `docs/deploy-*.md` — the wildcard preview domain is why it exists.

### A.3 — Merged OpenAPI

allauth serves its own spec at `/_allauth/openapi.json`; drf-spectacular serves `/api/v1/schema/`. Produce a single merged document for client generation, and a command or script that does the merge deterministically so CI can assert the generated client is not stale.

Deterministic matters: if the merge reorders keys run to run, the "client is stale" CI check fails randomly and gets disabled, and then it protects nothing.

### A.4 — Tests

- Signup → verification email → verify → authenticated session, end to end through the API.
- Password reset round-trip.
- Google OAuth: mock the provider at allauth's adapter layer. Do not require real credentials. Assert a user is created and a session established.
- TOTP enrolment and challenge **with the flag on**, and that the endpoints are absent with it off.
- Session listing and revocation.
- Cookie attributes asserted on the actual `Set-Cookie` header: HttpOnly, Secure, SameSite, Domain.
- The startup check fails on a mismatched domain.
- 401 body matches the Phase 1 error envelope.

### A.5 — Report the seam

The web worktree needs, precisely: the CSRF token acquisition flow, the exact cookie names, the login/signup request and response shapes including the partially-authenticated "awaiting TOTP" state, and how a 401 differs from a 403 on the wire. Write it into `docs/auth-client-contract.md`. This is a deliverable, not a courtesy.

---

# Worktree B — `p2-auth-web`

### B.1 — API client plumbing

- `orval` configured in `packages/api-client` against the merged spec, producing typed fetch functions, TanStack Query hooks and Zod schemas.
- Until worktree A lands its merged spec, generate against allauth's published spec shape from the PRD §7 endpoint list. Expect to regenerate; do not hand-write types you will throw away, and **never hand-edit `packages/api-client`**.
- Every request uses `credentials: 'include'`. CSRF header attached on unsafe methods.
- A single fetch wrapper that maps the error envelope to a typed error, distinguishing 401 / 402 / 403 / 404 / 409 / 422 / 429. The PRD's "Permission denial" flow says these get four different treatments; the client cannot do that if the wrapper flattens them.

### B.2 — Auth routes

The `(auth)` route group — no chrome, centred card:

`/login`, `/signup`, `/verify-email`, `/verify-email/[key]`, `/reset-password`, `/reset-password/[key]`, `/mfa`.

`/invite/[token]` and `/onboarding` are **Phase 3** — do not build them. Leave `/onboarding` as a redirect target that 404s honestly rather than a stub that pretends.

Forms use react-hook-form with the generated Zod schemas. Field errors from a 400 map to the correct field — that is a Phase 6 acceptance criterion but the mapping helper belongs here, with the first real consumer.

### B.3 — Account routes

`/account/profile`, `/account/security` (password, MFA devices), `/account/sessions` (list, revoke).

These render outside `AppShell`, which is Phase 6. Use the minimum layout that is honest; do not build a shell that Phase 6 will replace.

### B.4 — Route guards

Next middleware: unauthenticated access to `/app/*` and `/account/*` redirects to `/login?next=…`. Authenticated access to `/login` and `/signup` redirects onward.

The middleware must not be the enforcement point — the API is. Say so in a comment, because the next person to read it will assume otherwise.

### B.5 — Tests

- Vitest on the fetch wrapper's status mapping and the form-error mapper.
- Playwright: signup, login, logout, password reset. Against the real API and Mailpit — the PRD requires the verification email to be caught at `localhost:8025`, so drive the flow through it rather than stubbing.
- `axe-core` on every auth route. WCAG 2.1 AA is a floor, not a Phase 8 afterthought, and auth pages are the cheapest place to establish the habit.

---

## Acceptance — both worktrees, evidence required

From PRD §8 Phase 2:

- [ ] Signup → verification email in Mailpit → click → authenticated session
- [ ] Google OAuth completes and creates a user (provider mocked; no real credentials)
- [ ] Password reset round-trips end to end
- [ ] Session cookie is HttpOnly, Secure, SameSite=Lax, scoped to the parent domain — asserted on the header
- [ ] Unauthenticated access to `/app/*` redirects to `/login?next=…`
- [ ] TOTP enrolment and challenge work when the flag is enabled, and the endpoints are absent when it is not
- [ ] A user can list and revoke their own sessions
- [ ] Playwright covers signup, login, logout, reset
- [ ] The startup check fails loudly on a `SESSION_COOKIE_DOMAIN` that is not a parent of the app domain
- [ ] The merged OpenAPI document is deterministic run to run, and CI fails if the committed client is stale
- [ ] `docs/auth-client-contract.md` exists and is accurate
- [ ] `axe-core` reports zero violations on every auth and account route
- [ ] No migrations were generated

---

## How to work

- Strict TDD on the API worktree. Tests alongside the code on the web worktree, using the `mattpocock-skills:tdd` skill.
- Verify, do not assert. Every box needs pasted output.
- Update the Orca worktree comment at each task boundary.
- Commit in coherent chunks. Do not push and do not open a PR — the orchestrator merges.
- Every commit message body ends with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AQXQvAv8g92xotjrnnibLc
```

## Report back

Acceptance boxes with evidence; decisions the plan did not cover; anything in the PRD that looked wrong from inside the code; and — for worktree A — the client contract, in the doc and summarised in the report.
