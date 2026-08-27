# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Keel has not cut a release yet — everything below is `[Unreleased]`, grouped
by the phase it landed in. Phase numbers and plans are in `docs/plans/`.

## [Unreleased]

### Phase 8 — Observability and hardening

- Audit meta-test over the service registry; staff impersonation (admin
  action, exit endpoint, banner) with service-layer restrictions
- Audit read surface and settings tab
- Sentry (backend and frontend, `send_default_pii: False`) and PostHog
- DRF rate limiting with `Retry-After`, security headers, app-route CSP
- `axe-core` accessibility checks on app routes; k6 smoke test on the
  widget list

### Phase 7 — Marketing site

- `(marketing)` route group and landing page
- Human labels for pricing-page feature codes
- MDX blog via content-collections
- Sitemap, `robots.txt`, OG images, JSON-LD

### Phase 6 — Application shell and subdomain routing

- Host-based middleware splitting `app.lvh.me` from the marketing/auth apex
- `<AppShell>` and the shared component kit
- Widget vertical slice (full CRUD, end to end) as the reference resource
- Command palette with resource search; `<DataTable>` sort/filter/paginate
- Real-browser cross-host login test

### Phase 5 — Async work, email, and file uploads

- Celery queues (`default`, `email`, `external`, `scheduled`), the Tier 1
  task shim, retry/dead-letter/redrive
- Six scheduled jobs (plan sync, invitation expiry, trial-ending notices,
  dunning check, audit log retention, session cleanup)
- react-email templates rendered via Resend; allauth email routing
- R2/S3-compatible presigned uploads, MinIO in dev, `<FileUpload>`
- Job registry with a resumable runner, idempotency, per-org concurrency,
  and SSE (`useJobStream`, `<JobTray>`)

### Phase 4 — Billing and credits

- Append-only credit ledger with serialised holds and a daily cap
- `rebuild_credit_balances` management command; operator credit
  adjustments in Django admin, reasoned and audited
- Stripe plan/price sync, checkout, portal, subscription read
- Stripe webhook handling — signature verification, idempotency, async
  dispatch
- Entitlements (`check_feature`, `check_limit`), seat gating, dunning
  (access is not immediately revoked)
- Pricing page, billing settings, usage gates and meter, billing banners

### Phase 3 — Organisations, permissions, and tenancy

- `organizations/permissions.py` — the permission registry and
  `has_perm` as the single source of truth
- Preset role seeding
- The two CI meta-tests: permission-guard coverage, and the tenant
  isolation walk (404, not 403, across organisations)
- Permission-check placement lint
- Organisation services, selectors, serializers, viewsets
- Organisation switcher, onboarding, invitations, settings (frontend)

### Phase 2 — Authentication

- allauth headless wiring; cookie, CORS, and CSRF configuration for the
  cross-host session
- Deterministic OpenAPI merge and the generated TypeScript API client
- Auth and account routes, route guard middleware
- End-to-end auth tests; 401-vs-403 fix; MFA flag coverage
- Playwright + `axe-core` for auth and account routes

### Phase 1 — Core domain primitives

- `jobs` and `connections` apps, ID scheme, base models, error envelope
- `keel/core/authz.py` — the authorization registry and `Decision` type
- Audit decorators (`@audited` / `@not_audited`), cursor pagination,
  the Tier 1 task shim
- Encryption seam for `Connection` tokens
- `User` model, the full data model, the one baseline migration
- DRF, drf-spectacular, CORS, and logging configuration

### Phase 0 — Toolchain and skeleton

- pnpm workspace (turbo, workspace config), `apps/web` Next.js 15
  skeleton, `packages/ui` theme contract and `packages/api-client` stub
- `apps/api` Django 6 skeleton with `uv`, `infra/compose.dev.yml`
- ruff, mypy, `import-linter`, and pre-commit configuration
- Per-directory coverage gate (`scripts/check_coverage.py`)
- `infra/compose.prod.yml` stub
- CI workflow (`.github/workflows/ci.yml`)
- pgvector verification and `docs/deploy-railway.md`
