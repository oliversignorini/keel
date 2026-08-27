# Phase 11 — Auth BFF hardening

**Source of truth:** Notion "Keel Phase 11 — Auth hardening", the direction proposal's §4, `docs/auth-client-contract.md`, `keel-prd.md` §4 "Auth architecture".
**Depends on:** Phase 10 merged.
**Size:** Medium.

---

## Read this before planning the work

The Notion task lists "Django remains the auth authority", "browser UI never
owns long-lived auth tokens" and "no localStorage token storage" as targets.
**All three are already true.** The session is an `HttpOnly` `sessionid`
cookie set by Django through allauth headless; nothing is in localStorage;
`docs/auth-client-contract.md` documents the whole contract.

The one thing in that list that is *not* true is the BFF. Today the browser
calls `api.lvh.me` **directly, cross-origin**, with `credentials: 'include'`
and an `X-CSRFToken` header. That works, and it is not what "Next.js is the
safe server boundary" means. This phase is about that gap and nothing else.

---

## Boundary

**In scope:** the request path between browser, Next.js server, and Django.
Route handlers, cookie forwarding, CSRF, CORS, origin configuration, and the
tests and documentation for all of it.

**Out of scope:**

| Thing | Owner |
|---|---|
| allauth configuration, MFA, password flows, email verification | Nobody — the auth *provider* is settled and working |
| The permission system | `organizations/permissions.py`, unchanged |
| Deployment env vars for the new origins | Phase 12 — coordinate, do not implement |
| Session model or auth backends | Nobody |

**No migrations.**

---

## The decision this phase must make first

Three shapes are viable, and the Notion task leaves the choice open. Decide
it explicitly, in `docs/adr/0002-…`, before writing code:

1. **Full BFF.** Every `/api/v1/…` call goes through a Next.js route
   handler that attaches the session cookie server-side. The browser never
   sees the API origin. Cleanest security story; costs a proxy layer and
   complicates streaming (`keel/jobs/sse.py` — SSE through a Next.js route
   handler needs care) and file uploads (presigned PUTs go direct to storage
   regardless, so check what actually changes).
2. **Server-component reads, direct writes.** Reads happen in RSCs with the
   cookie forwarded; mutations stay direct cross-origin.
3. **Keep the current shape,** and harden the cross-origin configuration
   instead — document it as a deliberate choice.

Recommend option 1 unless SSE or upload flow makes it materially worse. If
you land on 3, the ADR has to argue it against the direction lock, which
says BFF; that is allowed, but it must be argued, not defaulted into.

## Work

- Implement the chosen shape. If option 1: a single typed proxy path, not
  one handler per endpoint. `packages/api-client`'s mutator (`src/http/mutator.ts`)
  is where the base URL is decided — that is the seam.
- Lock down what the choice permits: `CORS_ALLOWED_ORIGINS`,
  `CSRF_TRUSTED_ORIGINS`, `ALLOWED_HOSTS`, `SESSION_COOKIE_DOMAIN`,
  `CSRF_COOKIE_DOMAIN`, `SameSite`, `Secure`. Under a full BFF, browser
  origin access to the API can narrow considerably — narrow it.
- `keel/core/checks.py` already fails `manage.py check` on a misconfigured
  cookie domain (`keel.core.E001`/`E002`). Extend it to the new invariants
  rather than adding a second mechanism.
- SSE and presigned uploads must keep working. Test both explicitly.
- Update `docs/auth-flow.md` (Phase 9.B) and `docs/auth-client-contract.md`.

## Acceptance — evidence required

- [ ] `docs/adr/0002-…` records the choice, the alternatives, and why
- [ ] Login, logout, session continuity, protected-route access and expiry all tested end to end
- [ ] Expired or cleared session on a protected route yields a real **401** and the UI recovers — the middleware only checks cookie *presence* and never validity, by design
- [ ] CSRF is enforced on every unsafe method; a request without the token fails, tested
- [ ] Cross-host redirects (apex ↔ `app.`) still work, tested
- [ ] SSE job status still streams; presigned upload still completes
- [ ] `manage.py check` fails on a misconfigured origin or cookie domain
- [ ] `docs/auth-flow.md` matches the implementation, diagram included
- [ ] No auth token in localStorage, sessionStorage, or any JS-readable cookie — asserted in a test, not by inspection

## Report back

The chosen shape and why; anything that got harder (SSE, uploads, dev
ergonomics); what Phase 12 now needs in env vars.
