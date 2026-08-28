# ADR 0002 — The Next.js BFF terminates every browser API call

**Status:** Accepted — 2026-08-28
**Decides:** which of the three request-path shapes the auth BFF hardening
work implements.
**Depends on:** ADR 0001 (Django Ninja).

---

## Context

Every target the Notion "Keel Phase 11 — Auth hardening" task lists —
Django as sole auth authority, no long-lived token in browser JS, no
`localStorage`/`sessionStorage` token — was already true going into this
phase. `sessionid` is an `HttpOnly` cookie set by Django through allauth
headless; nothing is in Web Storage; `docs/auth-client-contract.md`
documents the whole contract. The one thing not true: "Next.js is the
safe server boundary." The browser called `api.<domain>` directly,
cross-origin, with `credentials: 'include'` and an `X-CSRFToken` header
(`packages/api-client/src/http/mutator.ts`, pre-phase-11). It worked —
CORS plus `SESSION_COOKIE_DOMAIN`/`CSRF_TRUSTED_ORIGINS` correctly scoped
made it work — but it is not the shape the direction lock names.

Three shapes were on the table:

1. **Full BFF.** Every `/api/v1/…` and `/_allauth/…` call goes through a
   Next.js route handler that forwards it to Django server-side. The
   browser never talks to the API origin for a programmatic
   `fetch`/`XMLHttpRequest` call.
2. **Server-component reads, direct writes.** Reads happen in RSCs with
   the cookie forwarded; mutations stay direct cross-origin.
3. **Keep the current shape** and harden the cross-origin configuration
   instead (CORS/CSRF/cookie-domain hardening only).

## Decision

**Option 1 — full BFF**, implemented as one generic proxy, not one route
handler per endpoint:

- `apps/web/app/api/v1/[...path]/route.ts` forwards every
  `/api/v1/…` call to Django's real origin
  (`KEEL_API_INTERNAL_URL`, server-only — never shipped to the browser
  bundle). The same route detects the one streaming path
  (`…/jobs/stream/`) and forwards it to the separate ASGI stream service
  (`KEEL_API_STREAM_INTERNAL_URL`) instead, piping the response body
  through unbuffered rather than fetching-then-returning.
- `next.config.ts` rewrites `/_allauth/:path*` to
  `/api/internal/allauth/:path*` (Next.js treats a literal `app/_allauth`
  folder as a private, unrouted segment — the leading underscore is a
  framework convention, not available for a real route — so the rewrite
  is what lets the wire path stay exactly `/_allauth/…`, unchanged from
  what `packages/api-client`'s generated functions already call).
  `apps/web/app/api/internal/allauth/[...path]/route.ts` implements the
  actual handler and additionally normalizes every non-2xx allauth
  response into Keel's own `{error:{code,message,details}}` envelope
  before it reaches the browser (api-patterns finding 16 — see "What
  this settles" below).
- `packages/api-client/src/http/mutator.ts`'s `API_BASE_URL` becomes the
  empty string unconditionally: every generated call is now a
  same-origin relative fetch, proxied by whichever of the two route
  handlers above matches its path. There is no longer a
  `NEXT_PUBLIC_API_BASE_URL` read for this purpose.
- Django's `CORS_ALLOWED_ORIGINS` default narrows to `[]` (was
  `["http://localhost:3000"]`) — no browser `fetch`/`XHR` should reach
  Django directly with credentials any more, so an empty allow-list is
  now correct rather than merely permissive-by-omission, and doubles as
  defense in depth against a future call site that bypasses the proxy by
  accident.

### The one thing that stays genuinely direct: Google's own callback

`GoogleContinueLink` posts a real `<form>` (not `fetch`) to
`/_allauth/browser/v1/auth/provider/redirect` — a full top-level
navigation, never a JS-mediated network call — and this form's `action`
is now a same-origin relative path like every other call, proxied by
the same allauth route handler. `proxyRequest` forwards it with
`redirect: 'manual'`, which — in the Node/undici runtime a Route Handler
runs in, unlike a _browser's_ `fetch()` — returns the real 3xx response
(status and `Location` both readable) rather than an opaque one, so the
handler just relays Django's 302 to Google untouched; the browser's own
top-level form-submission navigation follows that redirect exactly as
if it had gone to Django directly.

The one hop that stays genuinely, unavoidably direct is what happens
_after_ Google: it redirects back to whatever `redirect_uri` was
registered with the provider, which is Django's own
`/accounts/google/login/callback/` — a headed, non-`/_allauth` URL that
was never routed through any Next.js route to begin with, and couldn't
be even if this ADR wanted it to be (Google, not this app, controls
that URL's host). That hop sets the `sessionid` cookie while the browser
is transiently on the Django host — safe, because
`SESSION_COOKIE_DOMAIN=.{registrable domain}` already makes the cookie
valid for the Next.js hosts (`app.*`/apex) it lands on next, the same
mechanism the pre-phase-11 direct-cross-origin design relied on. No
code change was needed for this leg; it is a property of the
authorization-code flow, not a choice this app makes.

## Why not option 2 or 3

**Option 2** (reads via RSC, writes direct) was rejected because it
keeps the exact CORS/CSRF surface option 3 does for every mutation —
which is most of what this phase exists to close — while adding a
second code path (RSC data-fetching with the cookie forwarded
server-side) that the existing client-heavy `apps/web` (every current
data hook is `"use client"` — `use-me.ts`, `org-context.tsx`,
`use-current-user.ts`) does not use anywhere today. Building it only
for phase 11 would mean maintaining two fetch mechanisms with no reads
actually migrated to the new one.

**Option 3** was the honest fallback if SSE or uploads made option 1
materially worse. They don't:

- **Presigned uploads never go through Django at all** — the browser
  PUTs straight to R2 (`apps/web/lib/files/api.ts`'s
  `uploadToPresignedUrl`, PRD §5, unchanged before and after this ADR).
  Only the JSON `createUpload`/`completeUpload` calls that mint/confirm
  the presigned URL go through the BFF, and those are ordinary JSON
  request/response — no different from any other proxied call.
- **SSE costs a real hop** (browser → Next.js → the stream service,
  instead of browser → stream service directly), but Next.js Route
  Handlers stream a `ReadableStream` body natively under the Node
  runtime — the proxy pipes Django's `text/event-stream` response
  through without buffering, so "streams live" is preserved. The
  `EventSource` call site (`apps/web/lib/jobs/use-job-stream.ts`)
  changes from an absolute cross-origin URL to a same-origin relative
  path and is otherwise untouched — reconnect/backoff/heartbeat
  semantics are unaffected because none of that logic lived in the
  transport hop being added.

Given that, arguing option 3 against the direction lock ("browser talks
to the API origin directly, hardened") would mean arguing "the added
complexity outweighs closing the actual gap this phase exists for" —
which isn't true here, so this ADR doesn't make that argument.

## What this settles from the review findings

- **api-patterns finding 5** (no security scheme published; `servers`
  dropped by `merge_openapi.py`'s `merge()`): `scripts/merge_openapi.py`
  now declares `sessionCookie` (`apiKey`/cookie/`sessionid`) and
  `csrfHeader` (`apiKey`/header/`X-CSRFToken`) security schemes, applies
  them per operation (safe methods need only the cookie; unsafe methods
  need both; `plans`/`stripe/webhook` are marked `security: []`;
  `invite/{token}` is marked optional), and publishes `servers: [{"url":
"/"}]` documenting that the BFF is the intended caller of this
  document's own origin. `merge()` now carries `servers`/`security`
  through instead of dropping them.
- **api-patterns finding 12** (`/me/` is an unbounded N+1): fixed
  independently of the BFF shape (`keel/organizations/views.py::me`,
  `keel/organizations/selectors.py::get_active_memberships_by_organization`,
  `keel/billing/entitlements.py::resolve_entitlements_bulk`) — three
  queries total regardless of organisation count, down from `2N+1`. Filed
  under this phase because "the auth BFF makes this hotter" per the
  review, not because the BFF shape itself required the fix.
- **api-patterns finding 16** (two error envelopes, one document
  version): the `/api/v1/internal/allauth/[...path]` route handler is
  now the one place that turns allauth's `{status, errors}` and
  `{status, data:{flows}}` error shapes into Keel's own
  `{error:{code,message,details}}`, reusing
  `@keel/api-client`'s already-tested `normalizeErrorEnvelope` (moved
  from a client-side "normalize after the fact" step to the actual wire
  contract). The browser now receives exactly one error envelope shape
  from every path it can reach, not two reconciled after receipt.
  `identityFetch` still calls `normalizeErrorEnvelope` itself as a
  no-op safety net (the function's first branch already passes a
  Keel-shaped body through unchanged) — kept deliberately rather than
  removed, so a route handler bug fails safe into "double-normalized,
  still correct" rather than "unnormalized, wrong."
- **ddia finding 25** (nothing checks the merged spec is backward
  compatible run to run): `scripts/check_openapi_compat.py`, a local
  script in keeping with the project's philosophy of running gates
  before they reach CI, rather than adding more Actions minutes. The
  pre-push hook layer that invokes it is built separately; this phase adds
  the script itself and documents the additive-only rule it enforces for
  `/api/v1`.

**posd finding 5** (`GlobalResource`/`OrgScopedResource` are declaration
bags) is _not_ touched here. It's tagged fold-into-phase-11 in the
review, but the actual change this phase makes to `/me/` is a selector
rewrite inside an existing global (non-org-scoped) route body — it does
not touch the resource-declaration mechanism the finding is about, which
only applies to org-scoped routes. Folding in the decorator/registry
redesign the finding actually asks for would mean touching every app's
`views.py` for a mechanism this phase's own scope doesn't reach. Left for
whichever phase actually adds a route through that seam next.

## Consequences

- **Dev ergonomics**: one more moving part locally — the Next.js dev
  server now needs `KEEL_API_INTERNAL_URL`/`KEEL_API_STREAM_INTERNAL_URL`
  pointed at wherever Django/the stream service actually run, instead of
  the browser needing to reach them directly. In this repo's `lvh.me`
  setup both still resolve to `localhost`-adjacent addresses, so nothing
  changes in practice — see `.env.example`.
- **What Phase 12 needs in env vars**: a real deployment sets
  `KEEL_API_INTERNAL_URL` to Django's private/internal address (e.g. a
  Railway internal hostname, not `api.<domain>`'s public one, if the
  platform offers a private network — otherwise the public one still
  works, just without that extra hop savings) and
  `KEEL_API_STREAM_INTERNAL_URL` to the stream service's equivalent.
  `NEXT_PUBLIC_API_BASE_URL` is gone entirely — nothing in the browser
  bundle needs Django's address any more, including the OAuth form
  (see above). `DJANGO_CORS_ALLOWED_ORIGINS` should stay unset (empty)
  in production unless a future phase adds a legitimate direct-browser
  caller.
- **New failure mode to watch**: the BFF is now a single process in the
  request path for every authenticated page load. A Next.js server that
  is up but cannot reach Django turns into every API call failing
  through the proxy rather than the browser's own network layer
  reporting a direct connection failure — unchanged in kind from any
  other server-side proxy, but worth naming since it wasn't a failure
  mode this app had before.
