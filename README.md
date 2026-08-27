# Keel

A Django 6 + Next.js 15 SaaS template. Auth, multi-tenant organisations with granular permissions, Stripe billing, background jobs, a marketing site, and an application shell — built once, instantiated per project.

`keel-prd.md` is the specification and the reasoning behind it. This file is how to run the thing.

**Status:** Phases 0–8 built and merged. Today this is a working application, not yet something you can instantiate — `init` is Phase 17.

`docs/review-2026-08.md` is the current state of the repository and the plan for the rest of it; `docs/plans/phase-9.md` onward are the worktree-sized specifications, and `docs/adr/` holds the decisions.

---

## Quick start

Prerequisites: Docker, Node 22+, pnpm 9+, Python 3.12+, and [`uv`](https://docs.astral.sh/uv/).

```bash
pnpm install
cp .env.example .env
grep '^NEXT_PUBLIC' .env.example > apps/web/.env.local

docker compose -f infra/compose.dev.yml up -d      # Postgres 17, Redis 7, Mailpit
pnpm --filter @keel/emails build                   # required before the API tests run
cd apps/api && uv run python manage.py migrate && cd ../..

pnpm dev
```

Then:

|                  |                               |
| ---------------- | ----------------------------- |
| Marketing + auth | http://lvh.me:3000            |
| Application      | http://app.lvh.me:3000        |
| API              | http://api.lvh.me:8000        |
| Django admin     | http://api.lvh.me:8000/admin/ |
| Mailpit          | http://localhost:8025         |

Create an admin user with `cd apps/api && uv run python manage.py createsuperuser`.

### Why `lvh.me` and not `localhost`

The session cookie has to be shared between the web origin and the API origin, which needs a `Domain` attribute on a real registrable domain. Browsers special-case `localhost` and handle `Domain=.localhost` inconsistently, so `app.localhost` would authenticate fine in production and fail in dev — the worst failure shape available, because it only shows up on the machine you would least expect it on.

`lvh.me` is a public DNS name whose wildcard resolves to `127.0.0.1`. It needs no setup, but it does depend on a third-party DNS record, so it fails offline. `docs/dev-setup.md` documents a hosts-file fallback.

---

## Layout

```
apps/
  api/          Django 6 + DRF. Domain logic in services.py, reads in selectors.py
  web/          Next.js 15, App Router. (marketing) (auth) (app) route groups
packages/
  api-client/   Generated from OpenAPI — src/generated is never hand-edited
  emails/       react-email templates, rendered to HTML at build
  ui/           theme.css token contract + shared components
infra/          compose files, Caddyfile, railway.json
docs/           architecture.md, auth-flow.md, diagrams/, deployment, dev setup, and the phase plans
scripts/        coverage gate, permission lint, OpenAPI merge
```

Every Django app has the same shape: `models.py` `services.py` `selectors.py` `permissions.py` `serializers.py` `views.py` `tasks.py` `admin.py` `tests/`. That uniformity is the point — nothing should have to be guessed at.

---

## The invariants worth knowing before you change anything

The full seven are in `docs/architecture.md` and §4 of the PRD, each with the file that enforces it — `docs/auth-flow.md` has the request-level picture for the auth-related ones. Four of them are enforced by tests that will fail on you rather than by convention:

**Authorization lives in one file.** `organizations/permissions.py` holds every permission code and guard. `has_perm` returns a `Decision`, not a bool, so a denial carries a machine-readable reason into the 403 body. A CI meta-test walks the registry and fails if any guard lacks both an allow and a deny test — and the deny test must assert the _reason_, because a guard that denies for the wrong reason passes a boolean test and fails a user.

**Tenant scoping is declared, never inferred.** Every viewset declares `organization_scoped = True` plus a `test_factory`, or a `GLOBAL_JUSTIFICATION` paragraph explaining why it is not tenant-scoped. A meta-test walks the router and asserts cross-organisation access returns **404, not 403** — existence is not disclosed across a tenant boundary. Every justification is printed in CI, so an exemption is a decision someone has to read rather than a line in a list.

**Every mutating service is audited.** `@audited(action)` or `@not_audited(reason=...)`, and a meta-test fails on anything that is neither.

**The schema is one baseline migration.** Every table was created once, with final columns. Feature work adds services and views, not migrations. A migration appearing in a feature branch means either a real gap or drift, and either is worth knowing about.

Coverage is gated per directory, not by one global number — `[tool.keel.coverage]` in `apps/api/pyproject.toml`, enforced by `scripts/check_coverage.py`.

---

## Commands

```bash
pnpm dev            # Django + Next, both hot-reloading
pnpm lint           # ruff + eslint + prettier
pnpm typecheck      # mypy + tsc
pnpm test           # pytest (with the coverage gate) + vitest

cd apps/api
uv run pytest                       # needs the email templates built first
uv run lint-imports                 # the keel/domain and keel/core contracts
uv run python manage.py makemigrations --check --dry-run
```

`pnpm --filter @keel/emails build` before running the API suite. A root `conftest.py` will tell you if you forget, because the alternative symptom is an unrelated-looking 500 several frames inside allauth.

---

## What is not done

- **`init`, `CLAUDE.md` and the slash commands.** Without them this is an app, not a template. `CLAUDE.md` and the commands are Phase 9; `init` is Phase 17.
- **No `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md` or `CHANGELOG.md`,** and no Dependabot. Phase 9.
- **`docs/architecture.md` does not exist** — the link below points at it anyway. Phase 9.B.
- **CI has no production or security gates:** no `check --deploy`, Bandit, `pip-audit`, `pnpm audit` or secret scanning. Phase 9.C.
- **No query-count tests anywhere.** Phase 16.A.
- **The API layer is DRF and is moving to Django Ninja** — `docs/adr/0001-django-ninja-over-drf.md`, implemented in Phase 10.
- **URL segment** is `/api/v1/organizations/…`; the PRD specifies `/orgs/`. Reconciled in Phase 10.C.
- **`GET /api/v1/plans/`** returns a bare array rather than the cursor envelope §7 requires of collections. Phase 10.C.
- **`e2e/auth-flows.spec.ts`** is written but not wired into CI — it needs the live API and Mailpit as service containers. Phase 9.C.
- **Stripe test clocks** (trial end, renewal, cancellation) are untested; they need a live test account. Everything else runs against `stripe-mock`.
- **No credentials** are configured for Stripe, Google OAuth, Resend, R2, Sentry or PostHog. Each is wired against a stub or local stand-in and works with the integration disabled.

---

## Deployment

`docs/deploy-railway.md` covers the Railway path, including the answer to whether the target Postgres ships `pgvector` — it does not by default, and the doc names the templates that do.

The SSE endpoint runs as a **separate uvicorn service** from the same image. A held-open connection under a sync worker pool exhausts it far below what request/response load testing suggests, and a proxy that buffers `text/event-stream` produces a job tray that shows nothing for four minutes and then everything at once. `infra/railway.json` declares both services.
