# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Entries are grouped by the phase they landed in during this template's
build.

## [Unreleased]

### Phase 19 — Generators as the agent capability surface (ADR 0004)

- **19.A** — `packages/cli` (`pnpm gen ...`), `templates/` as the source
  of the reference slice, `resource`/`readonly-resource`/`permission`/
  `sync-client` generators; `apps/api/keel/widgets/` becomes a committed
  render of `templates/resource` rather than hand-maintained; new
  `templates-lint` and `reference-slice-is-a-render` CI gates
  (`.github/workflows/generators.yml`)
- **19.B** — `job` generator (Tier 1 and Tier 2), `e2e` ship-gate
  generator, `generated-slice-passes-the-invariants` CI gate, every
  `.claude/commands/new-*.md` rewritten as a thin wrapper over the CLI,
  and a new `/plan-feature` command for briefs spanning more than one
  generator
- **19.C** — `--ui` frontend templates (list/detail/create pages,
  `fields-ui.ts`) so `pnpm gen resource --ui` provisions the Next.js
  route group too, and an `email` generator for transactional emails

## [1.0.0] - 2026-08-28

First tagged release. Phases 0–18: a working, instantiable multi-tenant
SaaS template.

### Phase 18 — Portfolio polish and v1.0

- README rewritten around what Keel is, who it's for, and what it is
  not; the invariants and an architecture diagram moved into the README
  itself
- Screenshots of the running application
- `CHANGELOG.md` finalised and tagged `v1.0.0`
- `.claude/commands/new-resource.md` and `new-email.md` degrade
  gracefully when the demo slice has been deleted; `infra/k6/README.md`
  documents that the smoke test targets the demo slice and is orphaned
  once `init --demo-slice delete` removes it

### Phase 17 — Template mechanics (`init`)

- `scripts/init.ts`: renames the project and tenant noun across content
  and file/directory names, applies feature toggles (marketing site,
  demo slice, billing shape, optional `domain/` layer), regenerates
  lockfiles/OpenAPI/the generated client, resets git history, and
  deletes the template-authoring files (itself included)
- `template-ci.yml` — a CI job that runs `init` against a throwaway
  config and asserts the result still boots and passes its own gates

### Phase 16 — Query hygiene, settings hardening, rendering guardrails, pre-push gates

- **16.A** — query-count tests on every list endpoint; the `ninja_*`
  modules folded into `authz`/`auth`/`pagination`/`error_handlers`/
  `throttle`/`api` (no more `ninja_` prefixes); selector/index audit
- **16.B** — `manage.py check --deploy` wired into CI with a hard error
  on a default `SECRET_KEY`; secrets and logging hardening
- **16.C** — rendering, validation, and async task-boundary guardrails
- **16.D** — local `git push` hook (`docs/pre-push.md`) mirroring CI's
  blocking gates, plus CI `check --deploy` annotation visibility

### Phase 15 — Jobs and audit foundations

- Hardened constraints on `Job`/`JobStep`/`FailedTask`, generalised
  idempotency beyond billing, an audit provenance hook

### Phase 14 — Billing and credits polish

- Constraint hardening on the credit ledger, webhook ordering
  guarantees, typed entitlements

### Phase 13 — Document storage foundation

- Typed upload/list responses, foundation for per-organisation document
  storage on top of the existing presigned R2/S3 uploads

### Phase 12 — Railway + Postgres deployment baseline (prep)

- `infra/railway.json`, the two-service (gunicorn + uvicorn/SSE) shape,
  Postgres/`pgvector` groundwork ahead of `docs/deploy-railway.md`

### Phase 11 — Auth BFF (ADR 0002)

- Every `/api/v1/…` and `/_allauth/…` call now goes through a Next.js
  server-side proxy (`apps/web/app/api/v1/[...path]/route.ts`,
  `.../api/internal/allauth/[...path]/route.ts`) instead of a direct
  cross-origin browser call — closes the last gap between the
  architecture direction and the running code

### Phase 10 — DRF to Django Ninja migration

- Every app (`widgets`, `audit`, `billing`, `jobs`, `files`,
  `organizations`) migrated from DRF to Django Ninja, invariant
  meta-tests rewritten against Ninja routers, DRF and drf-spectacular
  removed entirely
- `/api/v1/organizations/` renamed to `/api/v1/orgs/` to match PRD §7
- The OpenAPI pipeline switched to Ninja's native generation; the merge
  step and generated client unchanged downstream
- Every paginated list endpoint's OpenAPI schema typed; operation IDs
  and query params cleaned up

### Phase 9 — Repository metadata, docs, CI security gates, CLAUDE.md

- **9.A** — `LICENSE` (MIT), `SECURITY.md`, `CONTRIBUTING.md`, this
  changelog, GitHub issue/PR templates, Dependabot
- **9.B** — `docs/architecture.md`, `docs/auth-flow.md`,
  `docs/diagrams/system.md`
- **9.C** — CI security gates: Bandit, `pip-audit`, `pnpm audit`,
  Gitleaks secret scanning (`.github/workflows/security.yml`)
- **9.D** — `CLAUDE.md` and the `.claude/commands/` slash commands
  (`new-resource`, `new-readonly-resource`, `new-email`, `new-job`,
  `new-connection`, `new-permission`, `sync-client`,
  `check-invariants`)

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
