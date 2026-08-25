# Phase 6 — App shell, subdomain routing, and the demo resource

**Source of truth:** `keel-prd.md` v1.2 — §4 "Auth architecture" (the cookie/domain constraint), §5 Layout, Component inventory and Routes, §8 Phase 6.
**Depends on:** Phases 3–5, all merged. Phase 5.5 is running concurrently and owns `<JobTray>`.
**Size:** Large.

---

## Boundary

**In scope:** `<AppShell>`, `<OrgSwitcher>`, `<CommandPalette>`, `<DataTable>`, `<ResourceForm>`, `<PageHeader>`, `<EmptyState>`, dark mode, the dashboard, host-based subdomain routing, and the `Widget` resource end to end as the canonical vertical slice.

**Out of scope:**

| Thing | Owner |
|---|---|
| `<JobTray>`, `useJobStream`, SSE | Phase 5.5 — **running right now.** Mount the tray if it has landed; if it has not, leave a clearly-named slot in `<AppShell>` and say so |
| Marketing routes, blog, sitemap | Phase 7, merged — do not restructure them |
| Sentry, PostHog, audit UI, impersonation, rate limiting, `axe-core` in CI | Phase 8 |
| The `init` script | Phase 9 |
| `keel-prd.md`, anything under `docs/plans/` | The orchestrator |

**No migrations.** `Widget` exists from the Phase 1 baseline.

---

## 6.A — Subdomain routing (decided this phase, not in the PRD as written)

The operator has chosen to move the app shell from `localhost/app/[org]` to a subdomain. **This is a deliberate deviation from PRD §5's route table** — record it in your report so the PRD can be updated to match.

### Why a subdomain works with the auth model

PRD §4 "Auth architecture" already requires the API to sit on a subdomain of the app's registrable domain, with `Domain=.acme.com` on the session cookie. Adding `app.acme.com` alongside `api.acme.com` changes nothing about that: both remain subdomains of the same registrable domain, and the existing cookie continues to be sent to both. Production needs no new cookie thinking.

### Why dev cannot use `app.localhost`

`localhost` is special-cased by browsers and handling of a `Domain=.localhost` cookie attribute is inconsistent between them. The session cookie has to be shared between the web origin and the API origin, so `app.localhost:3000` talking to `localhost:8000` would likely fail to authenticate in dev while working in production — the worst possible failure shape.

**Dev therefore uses `lvh.me`**, a public DNS name whose wildcard resolves to `127.0.0.1`. Verified on this machine: `app.lvh.me` → `127.0.0.1`.

```
app.lvh.me:3000    → Next.js, the (app) route group
lvh.me:3000        → Next.js, the (marketing) route group
api.lvh.me:8000    → Django
Cookie: Domain=.lvh.me
```

Note the one real weakness and write it into the docs: `lvh.me` is a third-party DNS record, so it fails offline. Document the hosts-file fallback (`keel.test`) for anyone who needs it.

### The work

1. **Next middleware, host-based.** Inspect the `Host` header. `app.*` rewrites to the `(app)` route group; the apex serves `(marketing)`. Internal route-group structure stays as it is — the URL changes, the file layout does not.
2. **Keep the existing route-guard middleware working.** Phase 2 built it; unauthenticated `/app/*` redirects to `/login?next=…`. Under a subdomain the login page lives on the apex, so the redirect crosses hosts — get this right and test it, because it is the single most likely thing to break.
3. **Settings.** `SESSION_COOKIE_DOMAIN`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS` and `HEADLESS_FRONTEND_URLS` all move to the new shape. Phase 2's startup check already fails loudly on a `SESSION_COOKIE_DOMAIN` that is not a parent of the app domain — **make sure it still fires correctly** under the new arrangement rather than being quietly satisfied.
4. **`.env.example` and the dev docs** updated, including how to reach the app in dev and why it is not `localhost`.
5. **Sitemap and robots** must keep excluding the app — the app is now a different host, so re-check rather than assuming Phase 7's exclusions still apply.

**Acceptance for 6.A is behavioural:** log in on the apex, land on the app subdomain, still authenticated. If that does not work, nothing else in this section matters.

---

## 6.B — The app shell

Per §5 Layout — **top bar, no sidebar**, sticky, 56px:

`[Logo] [Org ▾] │ Dashboard  Widgets  Settings │ [⌘K] [◐] [avatar]`

- `<OrgSwitcher>` immediately after the logo. Tenant context always visible — §5 calls this the single most common source of "wrong data" confusion in multi-tenant apps.
- Content in a max-width container. On mobile the nav collapses into a sheet; **the org switcher stays in the bar.**
- Settings keeps its secondary horizontal tab row (General · Members · Roles · Billing), which Phase 3 built.
- Dark mode via `next-themes`, driving the `.dark` / `[data-mode="dark"]` selectors the token contract already defines. Do not add a second theming mechanism.

Phase 3 built a minimal `<OrgSwitcher>` and settings shell. Absorb them rather than duplicating.

---

## 6.C — The components

From shadcn, installed as needed. Built on top, in `packages/ui`:

| Component | Notes |
|---|---|
| `<AppShell>` | Top bar, content container, page header slot, and a named slot for Phase 5.5's `<JobTray>` |
| `<CommandPalette>` | ⌘K. Navigation, resource search, actions. Must be fully keyboard-reachable — it is a first-class navigation path per the accessibility floor, not a power-user extra |
| `<DataTable>` | TanStack Table: sorting, filters, column visibility, **cursor pagination**, row selection, bulk actions |
| `<ResourceForm>` | react-hook-form + the generated Zod schema. Field errors from a 400 map to the correct field — Phase 2 built the mapper, reuse it |
| `<PageHeader>`, `<EmptyState>` | Every empty state offers a primary action |

Cursor pagination, not offset — Phase 1 built the cursor paginator and the PRD requires the list page to stay fast at 50k rows.

---

## 6.D — The Widget vertical slice

**This is the most important deliverable in the phase.** PRD Phase 9 keeps it as `docs/reference-slice/` for `init`, because "make this look like the reference slice" is the most useful instruction to point Claude Code at during a months-long build.

Build it end to end, in the canonical order, with nothing skipped:

`models.py` (exists) → `services.py` → `selectors.py` → `permissions.py` → `serializers.py` → `views.py` → `tasks.py` → tests → client regeneration → list page → detail page.

Every file must earn its place and demonstrate the rule for that file. The viewset declares `required_permissions`, `organization_scoped = True` and `test_factory` — and the tenant-isolation meta-test will then walk it automatically, so **expect it to catch things**.

Register the widget permission codes properly: they go in `organizations/permissions.py` with allow and deny tests, and the guard meta-test will fail until they do.

---

## Acceptance — evidence required

- [ ] **Log in on the apex domain and land authenticated on the app subdomain** — driven in a real browser, not reasoned about
- [ ] Unauthenticated access to the app subdomain redirects to the apex login with a working `next`
- [ ] The `SESSION_COOKIE_DOMAIN` startup check still fails loudly on a mismatched domain
- [ ] Organisation switching updates the route and refetches all data
- [ ] Command palette navigates and searches resources **by keyboard alone**
- [ ] Data table sorts, filters, paginates by cursor, and bulk-deletes with permission checks
- [ ] Form errors from a 400 map to the correct field
- [ ] Widget CRUD works end to end with permission enforcement at every action
- [ ] Dark mode has no contrast failures
- [ ] Every empty state offers a primary action
- [ ] Zero hydration errors in the console on every app route — check by loading them
- [ ] Sitemap and robots still exclude the app now that it is a separate host
- [ ] No migrations were generated

---

## How to work

- Strict TDD on the backend half of the Widget slice. Tests alongside on the frontend, using `mattpocock-skills:tdd`.
- **Build the email templates before running the API suite:** `pnpm --filter @keel/emails build`. A root `conftest.py` will tell you, but knowing saves a cycle.
- **Drive it in a browser.** The only real frontend bug found so far was a hydration mismatch every unit test passed straight through, and 6.A's cross-host login cannot be verified any other way. Playwright is available.
- Run `ruff check`, `ruff format --check`, `mypy`, `pytest`, `eslint`, `prettier`, `tsc`, `vitest` before claiming done.
- Update the Orca worktree comment at each task boundary.
- Do not push, do not open a PR — the orchestrator merges.
- Every commit message body ends with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AQXQvAv8g92xotjrnnibLc
```

## Report back

Acceptance boxes with evidence; **the exact settings changes 6.A required**, so the PRD and the Phase 9 `init` prompts can be updated to match; whether `<JobTray>` had landed and what you did if not; anything in the PRD that looked wrong from inside the code.
