# Auth client contract (Phase 2, worktree A → worktree B)

What `p2-auth-web` needs to build against `p2-auth-api`'s allauth headless
configuration. Source of truth for exact request/response shapes is
allauth's own spec at `/_allauth/openapi.json` (merged into the generated
client per A.3) — this document is the map that makes that spec readable,
plus the things the spec alone won't tell you: which cookie carries the
session, how to get a CSRF token, and how a 401 differs from a 403.

## Base URL and client type

All identity endpoints are under `/_allauth/browser/v1/…` — the **browser**
client, not the **app** client (`/_allauth/app/v1/…`). The browser client is
cookie-based and CSRF-protected; the app client is bearer-token based via
`X-Session-Token` and is unused by this project (PRD §4: "the
`X-Session-Token` header path exists for non-browser clients and stays
unused"). Every request below assumes `/_allauth/browser/v1/` and
`credentials: 'include'`.

## Cookies

| Cookie | Set by | Purpose |
|---|---|---|
| `sessionid` | Django session middleware, on any authenticating response | The session. `HttpOnly`, `Secure` (in non-DEBUG), `SameSite=Lax`, `Domain` = registrable domain (e.g. `.acme.com`) in production, unset (host-only) in local dev. |
| `csrftoken` | Django CSRF middleware, on the first `GET` to any browser-client headless endpoint | Not `HttpOnly` — the SPA reads it and echoes it back as a header on unsafe methods. `SameSite=Lax`, `Secure` matches the session cookie. |

Both are `Domain`-scoped identically, controlled by `SESSION_COOKIE_DOMAIN`
/ `CSRF_COOKIE_DOMAIN` in `apps/api/config/settings/base.py`, which derive
from `KEEL_APP_DOMAIN`. A `manage.py check` failure (`keel.core.E001` /
`E002`) means that domain is misconfigured — see that file's comments
before touching cookie settings directly.

## CSRF token acquisition

Django's CSRF middleware only sets the `csrftoken` cookie on a response
that calls `django.middleware.csrf.get_token()` — and every headless
**browser**-client view does exactly that
(`allauth.headless.internal.decorators.browser_view`). Practically:

1. On app load, call `GET /_allauth/browser/v1/auth/session` (or
   `GET /_allauth/browser/v1/config`) once. The response sets `csrftoken`
   whether or not a session exists yet.
2. Read the cookie, send it back as the `X-CSRFToken` header on every
   `POST` / `PATCH` / `DELETE` to `/_allauth/browser/v1/…` and to
   `/api/v1/…` (Django's default CSRF settings; header name and cookie
   name are unchanged from Django's defaults).
3. `GET` requests never need the header.

## Response envelope — two different shapes on the wire

**This is the thing most likely to bite the client if missed.** The two
API surfaces do not share an envelope.

### `/_allauth/browser/v1/…` (allauth headless)

```json
{
  "status": 200,
  "data": { "...": "endpoint-specific" },
  "meta": { "is_authenticated": true }
}
```

On failure, allauth adds an `errors` array instead of (or alongside) `data`:

```json
{
  "status": 400,
  "errors": [
    { "message": "Already registered.", "code": "email_taken", "param": "email" }
  ]
}
```

`status` inside the body always matches the HTTP status code. There is no
`error.code` / `error.message` / `error.details` shape here — do not reuse
the Phase 1 error-envelope client-side error mapper for `/_allauth/`
responses. Build a second, small mapper for this shape, or adapt the
existing one to branch on which base path the request hit.

### `/api/v1/…` (DRF, this project's own endpoints)

```json
{ "error": { "code": "SEAT_LIMIT_EXCEEDED", "message": "...", "details": [...] } }
```

This is `keel/core/exceptions.py`'s envelope (PRD §7), unchanged from
Phase 1. `/api/v1/me/` and everything under `/api/v1/orgs/…` (Phase 3+)
uses this shape, not allauth's.

## 401 vs 403 vs 409 on `/_allauth/browser/v1/…`

- **401** — no session, or a session that is only *partially* authenticated
  (e.g. password verified, TOTP still pending). The body's `data.flows`
  array is the state machine: each entry has an `id` (e.g. `"login"`,
  `"signup"`, `"mfa_authenticate"`) and a pending entry has
  `"is_pending": true`. **This is the "awaiting TOTP" state** — the client
  detects it by finding the `mfa_authenticate` flow with
  `is_pending: true` in a 401 response's `data.flows`, not by a distinct
  status code. `meta.is_authenticated` is `false` in both the "no session"
  and "pending" cases — check `data.flows` to tell them apart, not `meta`.
- **403** — an action is disallowed for a reason that isn't "log in" (e.g.
  signup attempted while `ACCOUNT_LOGIN_METHODS`/`is_open_for_signup`
  forbids it, or a social-provider action needs re-authentication it
  can't silently do).
- **409** — a conflict with current state (e.g. signing up while already
  authenticated, confirming an email link twice, re-requesting a
  password reset for an in-progress reset). No `errors` array is
  guaranteed on a 409; treat it as "refresh and re-check session state",
  not as a field-level validation error.
- **429** — rate limited (`ACCOUNT_RATE_LIMITS`, base.py). Standard
  `Retry-After` header semantics are not guaranteed by allauth the way
  they are by `/api/v1/`'s DRF throttling — poll `data.flows` / retry
  after a client-chosen backoff rather than relying on a header.

`/api/v1/…` 401/403 follow the PRD §7 table exactly (401 = no/expired
session, 403 = authenticated but denied, `code` = `Decision.reason`).

## Endpoints in use (Phase 2 scope)

```
GET    /_allauth/browser/v1/config                       # capabilities, no auth required
GET    /_allauth/browser/v1/auth/session                 # current session / triggers CSRF cookie
DELETE /_allauth/browser/v1/auth/session                 # logout
POST   /_allauth/browser/v1/auth/signup                  # { email, password1, password2 }
POST   /_allauth/browser/v1/auth/login                   # { email, password }
POST   /_allauth/browser/v1/auth/password/request        # { email } — request reset
POST   /_allauth/browser/v1/auth/password/reset           # { key, password1, password2 }
POST   /_allauth/browser/v1/auth/email/verify             # { key }
POST   /_allauth/browser/v1/auth/email/verify/resend
GET    /_allauth/browser/v1/auth/provider/redirect        # ?provider=google&callback_url=…&process=login
                                                            # headed redirect — browser navigation, not fetch()
POST   /_allauth/browser/v1/auth/provider/token           # token-based social login (unused; PKCE redirect flow is)
GET    /_allauth/browser/v1/auth/sessions                 # list this user's active sessions (allauth.usersessions)
DELETE /_allauth/browser/v1/auth/sessions                 # revoke sessions (body selects which; see spec)

# MFA (TOTP) — present only when KEEL_MFA_ENABLED=true (see apps/api .env.example)
POST   /_allauth/browser/v1/account/authenticators/totp   # activate — response includes the TOTP secret URI
GET    /_allauth/browser/v1/account/authenticators/totp
DELETE /_allauth/browser/v1/account/authenticators/totp
POST   /_allauth/browser/v1/auth/2fa/authenticate         # { code } — resolves a pending mfa_authenticate flow
```

Exact request/response bodies, including field names, are generated from
`/_allauth/openapi.json` — do not hand-transcribe them a second time here;
this list is for orientation and for endpoints not obvious from the spec
alone (the redirect flow, the pending-flow shape).

### Google OAuth (social login)

There is no `fetch()` call for this flow. `GET
/_allauth/browser/v1/auth/provider/redirect?provider=google&process=login&callback_url=<frontend-url>`
is a **full-page browser navigation** (`window.location.href = …`, not
`fetch`) — it 302s to Google, and Google redirects back through allauth,
which sets the session cookie and then redirects to `callback_url` on the
frontend. The frontend route at `callback_url` should immediately call
`GET /_allauth/browser/v1/auth/session` to read the resulting
authenticated/partial state, the same as after any other login call.

### `/verify-email/[key]` and `/reset-password/[key]`

These Next.js routes are where `HEADLESS_FRONTEND_URLS` (base.py) points
the confirmation/reset emails. The route reads `key` from the URL and
`POST`s it to `/_allauth/browser/v1/auth/email/verify` or
`/_allauth/browser/v1/auth/password/reset` respectively — the emailed link
is not itself an API call the browser makes automatically.

`/invite/[token]` is **not** an allauth concept — it's Phase 3
(organizations). Do not wire it against `HEADLESS_FRONTEND_URLS`.

## MFA flag

`KEEL_MFA_ENABLED` (apps/api env var) controls whether `allauth.mfa` is
installed at all. When `false` (the default), the TOTP endpoints above
return 404 — `allauth.mfa` isn't registered, so the headless router never
adds them (`allauth.headless.urls.build_urlpatterns` gates on
`allauth_settings.MFA_ENABLED`, which reflects whether the app is
installed). The client should treat a 404 on
`/_allauth/browser/v1/account/authenticators/totp` as "MFA is off for this
deployment", not as an error — and can confirm this ahead of time via
`GET /_allauth/browser/v1/config`, whose `data.mfa` key is present only
when MFA is enabled.

## Merged OpenAPI spec

`/api/v1/schema/` (drf-spectacular) and `/_allauth/openapi.json` (allauth)
are merged deterministically by `scripts/merge_openapi.py` (A.3) into
`openapi.merged.json` at the repo root, which `packages/api-client`'s
`orval` config points at. Regenerate the client after any settings change
here that alters allauth's exposed surface (flipping `KEEL_MFA_ENABLED`,
adding a social provider, etc.) — CI fails if the checked-in client is
stale relative to a fresh merge.
