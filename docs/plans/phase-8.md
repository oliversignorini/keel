# Phase 8 — Observability, audit, hardening

**Source of truth:** `keel-prd.md` v1.2 — §4 invariant 7, the Integration points table, §6 "Impersonation", §8 Phase 8, and the v1.2 note specifying `@audited` / `@not_audited`.
**Depends on:** Phases 3–6, all merged.
**Size:** Medium.

---

## Boundary

**In scope:** Sentry on both runtimes, PostHog, the audit meta-test and audit settings page, staff impersonation with its restrictions, API rate limiting, security headers, `axe-core` in Playwright, a k6 smoke test.

**Out of scope:**

| Thing | Owner |
|---|---|
| Renaming `/api/v1/organizations/` to `/api/v1/orgs/` | A conformance pass that runs straight after this phase — **do not touch URL shapes** |
| Cursor-envelope for `GET /api/v1/plans/` | Same conformance pass |
| Wiring `e2e/auth-flows.spec.ts` into CI | Same conformance pass |
| The `init` script, `CLAUDE.md`, slash commands | Phase 9 |
| `keel-prd.md`, anything under `docs/plans/` | The orchestrator |

**No migrations.** `AuditLog` exists from the Phase 1 baseline, with `actor`, `impersonator`, `action`, `target_type`, `target_id`, `metadata`, `ip`, `user_agent`.

---

## What already exists — do not rebuild

Phase 1 built `keel/core/audit.py` with `@audited(action)` and `@not_audited(reason)`, both registering into a walkable module-level registry. Phases 3–6 have been decorating services with them throughout. Your job is the **meta-test over that registry**, the read surface, and impersonation — not the decorator.

---

## Tasks

### 8.1 — The audit meta-test

PRD v1.2, Phase 8: walk every `services.py`, collect the public callables that mutate, and fail on any carrying neither `@audited` nor `@not_audited(reason=...)`. Print every `not_audited` reason in CI output, on the same principle as `GLOBAL_JUSTIFICATION` — an escape hatch that costs a sentence and appears in every run is a decision; a silent exemption is where drift hides.

**Demonstrate it failing.** Strip the decorator off a real mutating service, paste the failure, restore it. A meta-test that has never failed is a meta-test that does not work — that has caught two real gaps in this project already.

Also assert an audited service writes **exactly one** audit row per call, on commit, carrying actor and impersonator.

### 8.2 — Audit read surface

`GET /api/v1/organizations/{slug}/audit/` behind `audit.view`, cursor-paginated. **Keep the existing URL shape** — the rename is the next pass's job and doing it here means two agents editing the same routes.

Settings page at `/[org]/settings/audit`, as a fifth tab alongside General · Members · Roles · Billing. PRD §5 lists it; Phase 3 built the tab row without it.

### 8.3 — Impersonation

Staff-only, from Django admin. On start: an `impersonation.start` audit row recording both impersonator and actor. Every subsequent audit row carries the impersonator. `<ImpersonationBanner>` renders on every page and **cannot be dismissed**. Exit writes `impersonation.end`.

**The four restricted actions, enforced in services and not in the UI** (PRD §6): an impersonated session cannot change password, manage MFA, start or cancel a subscription, or delete the organisation. Test each by calling the service directly with an impersonated session — a UI-level check proves nothing.

### 8.4 — Sentry

Both runtimes, releases tied to the git SHA, source maps uploaded. Phase 5 left a no-op seam for the dead-letter path — wire it up.

No DSN exists. Everything must work with Sentry disabled and be provably wired when enabled: assert the event payload against a transport stub rather than requiring a live project. Say plainly which criteria need a real DSN.

### 8.5 — PostHog

Client-side, plus a server-side capture helper for billing events. Same treatment: no key, so prove the call shape against a stub.

### 8.6 — Rate limiting and headers

API rate limiting returning **429 with `Retry-After`** — Phase 1's exception handler already maps that status, so use it rather than inventing a second shape. allauth's own limiter already covers auth endpoints; this is the general API.

Security headers: HSTS, `X-Content-Type-Options`, `Referrer-Policy`, and a CSP. Be careful with the CSP — the app is on `app.<domain>` and the API on `api.<domain>`, so `connect-src` must allow the API origin or every request fails in production only.

### 8.7 — `axe-core` and k6

`axe-core` in Playwright on **all** routes, not just the auth ones Phase 2 covered — marketing, app, settings, widgets. Zero violations is the criterion; WCAG 2.1 AA is the floor.

k6 smoke test: 100 rps on the widget list with p95 under 300ms. If the machine cannot produce a meaningful number, say so and record what you did measure rather than reporting a fabricated pass.

### 8.8 — Two small fixes

- `CreditLedgerEntry` renders in Django admin as "Credit ledger entrys". Add `verbose_name_plural`.
- Both hosts 404 on `/favicon.ico`. Add one.

---

## Acceptance — evidence required

- [ ] A deliberate error appears in Sentry with the correct release and readable stack — or, without a DSN, the payload is asserted against a stub and the gap is named
- [ ] Every mutating service is decorated `@audited` or `@not_audited(reason=...)`; the meta-test fails on any that is neither, **demonstrated by stripping one**, and prints every reason
- [ ] An audited service writes exactly one audit row per call, on commit, with actor and impersonator
- [ ] Impersonated sessions are recorded and **cannot perform the four restricted actions** — each tested at the service layer
- [ ] The impersonation banner renders on every page and cannot be dismissed
- [ ] Rate limits return 429 with `Retry-After` in the standard error envelope
- [ ] `axe-core` reports zero violations on all routes, including marketing and app
- [ ] k6 sustains 100 rps on the widget list with p95 under 300ms, or the limitation is stated with real numbers
- [ ] CSP allows the API origin from the app origin — verified in a browser, since this fails in production only
- [ ] Audit tab appears in settings and is gated by `audit.view`
- [ ] No migrations were generated, and no URL shapes were changed

---

## How to work

- Strict TDD on the backend. Tests alongside on the frontend.
- **Build the email templates before running the API suite:** `pnpm --filter @keel/emails build`.
- Dev runs on `lvh.me` now: `lvh.me:3000` marketing, `app.lvh.me:3000` app, `api.lvh.me:8000` API, admin at `api.lvh.me:8000/admin/`. See `docs/dev-setup.md`.
- **Drive it in a browser.** The CSP criterion and the banner cannot be verified any other way.
- Run `ruff check`, `ruff format --check`, `mypy`, `pytest`, `eslint`, `prettier`, `tsc`, `vitest` before claiming done.
- Update the Orca worktree comment at each task boundary.
- Do not push, do not open a PR — the orchestrator merges.
- Every commit message body ends with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AQXQvAv8g92xotjrnnibLc
```

## Report back

Acceptance boxes with evidence; the pasted output of the audit meta-test failing and then passing; which criteria need real Sentry/PostHog credentials; the k6 numbers you actually measured; anything in the PRD that looked wrong from inside the code.
