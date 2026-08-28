# Architecture

The seven invariants, verbatim from `keel-prd.md` §4 "Architecture
Invariants" — this file states each plainly, names what enforces it, and
then walks the request path and the layout that follow from them.

If a section here and `keel-prd.md` §4 ever disagree, the PRD wins; this
file is meant to stay a faithful restatement, not a second source of truth.

---

## The seven invariants

### 1. Domain logic lives in `services.py` and `selectors.py`

Views, schemas, Celery tasks, Django admin, management commands,
database triggers, and the Next.js client hold no business rules. A view
parses, calls a service, serializes, returns. A Celery task body is a
single call into a service.

Some projects also carry an optional third layer, `keel/domain/`, for pure
rules worth isolating from Django entirely (scoring, pricing, ledger
arithmetic) — no ORM, no HTTP, no Celery. `services.py` may call
`domain/`; `domain/` may never call anything back. This repo has not yet
created `keel/domain/`, so the layer is inert rather than absent-by-design:
`import-linter`'s contract for it activates the moment anything is added
there.

**Enforced by:** convention plus code review, not a CI gate — this is the
one invariant with no automated check today. `apps/api/keel/widgets/`
(`services.py`, `selectors.py`) is the reference shape every other app
follows; since Phase 19 it is a generated render of `templates/resource`
rather than hand-maintained (see "Generators" below), so the shape stays
correct by construction for anything provisioned with `pnpm gen`.

### 2. Authorization is expressed only in `organizations/permissions.py`

A registry of named permission codes plus one function,
`has_perm(user, organization, code, subject=None)`, returning a
`Decision(allowed, reason, details)` — never a bare bool. A Ninja
resource declares `required_permissions`; its route function calls
`resolve_and_authorize` (`keel/core/authz.py`), which resolves the
organisation and runs `has_perm` for each required code before the
handler body executes. Permission logic must not appear in views,
schemas, querysets, templates, or the client — the client's `/me`
permission list is for deciding what to render, never for enforcement.

The `Decision` dataclass, the `Guard` protocol, and the registry object
live in `keel/core/authz.py` (a dependency-ordering split: `keel/core`
cannot import `keel/organizations`), but no permission code, role, or rule
lives there — only the vocabulary. The codes and their guard
implementations live in `organizations/permissions.py`.

**Enforced by:**

- `scripts/check_permission_lint.py` — greps for `Decision.allow(` /
  `Decision.deny(` / `registry.register(` outside
  `keel/organizations/permissions.py` and fails the build on a hit.
- A CI meta-test walks the guard registry and fails if any entry lacks
  both an allow test and a deny test; deny tests must assert the
  `reason`, not just that access was refused.
- `[tool.keel.coverage]` in `apps/api/pyproject.toml` holds
  `keel/organizations/permissions.py`, `resolvers.py`, and `roles.py` to
  100%.

### 3. One `transaction.atomic()` per service function, opened inside the service

Never in the view. Multi-step operations that touch Stripe mutate local
state inside the transaction, then dispatch the external call via
`transaction.on_commit()` — nothing calls Stripe from inside an open
transaction. Webhook processing is the mirror image: record the
`StripeEvent` row first for idempotency, then apply the state change in an
atomic block, so replaying an event is a no-op by construction.

**Enforced by:** convention and code review, plus a test suite requirement
— PRD §4 requires a test that replays every handled Stripe webhook event
type twice (`apps/api/keel/billing/`). There is no static check that a
transaction boundary sits in the right file; this is the second invariant
without an automated gate.

### 4. Schema changes happen only through Django migrations

In version control, reviewed, reversible where practical. No dashboard,
console, or admin interface may alter schema — Railway's database UI is
for inspection only. Every table was created once with final columns; a
migration appearing in a feature branch means a real gap or drift.

**Enforced by:** `manage.py makemigrations --check --dry-run` in CI's
`test-api` job, which fails the build if model state and migrations
disagree. (Not yet wired to `check --deploy`'s production-settings run —
see 9.C.)

### 5. Async work runs on Celery, with an explicit two-tier boundary

Tier 1 — fire-and-forget, single-step work (send an email, sync a Stripe
object) — goes through the thin `@task` / `.enqueue()` shim in
`keel/core/tasks.py`, which mirrors Django 6's `django.tasks` surface
while executing on Celery. Tier 2 — multi-step jobs that commit
intermediate results, resume after a crash, and stream progress — uses
Celery directly (`keel/jobs/`) and must not be squeezed into the Tier 1
shim. Four queues, routed by cost profile: `default`, `email`, `external`,
`scheduled`, so a backlog in one cannot starve another.

**Enforced by:** `[tool.keel.coverage]` holds `keel/core/tasks.py` to
100%; the Tier 1/Tier 2 split itself is a convention documented in
`keel/core/tasks.py`'s own module docstring and in `keel/jobs/`, not a
static check — a Tier 2 job written against the Tier 1 shim would pass CI.

### 6. Validation has two mandatory layers

Ninja `Schema` classes (`schemas.py`, Pydantic-native) validate shape at
the HTTP edge and reject malformed input with 400. Services enforce
invariants and raise typed domain exceptions (`keel/core/exceptions.py`'s
`DomainError` hierarchy) that map to 409 or 422. Client-side Zod
validation exists for UX responsiveness only and is never enforcement —
the Zod schemas are generated from the same OpenAPI spec as the rest of
the client, so they cannot drift from the server's shape contract.

**Enforced by:** `keel/core/error_handlers.py`'s Ninja exception handlers
(registered once on the shared `NinjaAPI` instance, `keel/core/api.py`),
the single place the `{ "error": { "code", "message", "details" } }`
envelope is built — a service that raises a plain `Exception` instead of
a `DomainError` subclass surfaces as an unhandled 500, which is itself
the signal that the boundary was skipped.

### 7. Testing is layered, and coverage is gated per directory, not by one global number

`--cov-fail-under` takes one number for the whole run; per-path floors are
a `[tool.keel.coverage]` table in `apps/api/pyproject.toml`, read by
`scripts/check_coverage.py` after pytest, which exits non-zero naming
every path that missed (with actual vs. required) and fails on a glob
that matches nothing (a directory renamed or deleted with its obligation
left behind).

Tenant scoping is declared, never inferred — every Ninja resource states
`organization_scoped = True` with a `test_factory`, or `organization_scoped
= False` with a `GLOBAL_JUSTIFICATION` paragraph, checked at import time
by `__init_subclass__` on `GlobalResource` / `OrgScopedResource`
(`keel/core/authz.py`). A meta-test
(`keel/organizations/tests/test_meta_router_wiring.py`) walks the live
URLconf so a scoped resource cannot go unwired, and
`keel/organizations/tests/test_ninja_tenant_isolation.py` builds a row in
organisation A, gives an org-B member every required permission, and
asserts **404, not 403** — existence is not disclosed across a tenant
boundary.

**Enforced by:** `scripts/check_coverage.py` (coverage floors),
`test_meta_router_wiring.py` and `test_ninja_tenant_isolation.py` (tenant
scoping), and the `contracts` CI job, which re-derives
`openapi.merged.json` and fails on drift against the checked-in generated
client.

---

## Request path: browser to database

```
browser
  │  fetch(..., { credentials: 'include' })
  │  Cookie: sessionid (+ X-CSRFToken on unsafe methods)
  ▼
Next.js 15 (App Router) — (marketing) (auth) (app) route groups
  │  cross-origin call to the API host; see "Note on the pipeline" below
  ▼
Django 6 + Ninja — sync, gunicorn
  │
  ├─ SessionMiddleware / CSRF middleware       → resolves the session
  ├─ resolve_and_authorize()                   → calls has_perm() (invariant 2)
  ├─ route function                            → keel/<app>/selectors.py (reads)
  ├─ route function                            → keel/<app>/services.py (writes,
  │                                                transaction.atomic() per call)
  └─ Ninja Schema (schemas.py)                 → shape validation, response body
  │
  ▼
Postgres 17            Redis 7 (broker + cache)
                              │
                    Celery worker / Celery beat
                     (Tier 1 shim or Tier 2 jobs)
```

A parallel path exists for the SSE job-status stream
(`/api/v1/.../stream`): the same Django code runs under a **separate ASGI
service** on uvicorn, because a held-open connection under the sync
worker pool exhausts it at a request count far below what
request/response load testing suggests. `infra/railway.json` declares
both services from the same image.

**Note on the pipeline today.** Since Phase 11
(`docs/adr/0002-auth-bff-shape.md`), the browser no longer calls
`api.lvh.me` directly for any programmatic `fetch`/`XMLHttpRequest` —
every `/api/v1/…` and `/_allauth/…` call is same-origin against Next.js,
which forwards it to Django server-side
(`apps/web/app/api/v1/[...path]/route.ts`,
`apps/web/app/api/internal/allauth/[...path]/route.ts`). Session handling
was already correct before this (Django is the sole authority, the
cookie is `HttpOnly`); this closed the remaining gap — the direct
cross-origin call was not the BFF pattern the architecture direction
locks in. `docs/auth-flow.md` has the full request-path diagram.

---

## App layout

```
apps/api/
├── config/
│   ├── settings/{base,dev,prod,test}.py
│   ├── urls.py
│   ├── celery.py
│   └── asgi.py
├── keel/
│   ├── domain/          # OPTIONAL pure layer — not created in this repo yet
│   ├── core/            # base models, mixins, exceptions, pagination,
│   │                     # task shim, org scoping, authz vocabulary
│   ├── accounts/         # User, profile, allauth glue
│   ├── organizations/    # Org, Membership, Role, Invitation, PERMISSION REGISTRY
│   ├── billing/          # Plan, Price, Subscription, entitlements, Stripe webhooks
│   ├── audit/             # AuditLog, impersonation
│   ├── notifications/     # email dispatch
│   ├── files/             # presigned R2/S3 uploads
│   ├── jobs/               # Job, JobStep, FailedTask — Tier 2 primitive
│   ├── connections/        # third-party OAuth Connection
│   └── widgets/             # demo resource — `init` (Phase 17) deletes this
└── tests/
```

Every domain app under `keel/` shares one file shape:

```
<app>/
├── models.py         # data shape only
├── services.py       # ORM, transactions, side effects — all writes
├── selectors.py       # all reads
├── permissions.py     # required permission codes (organizations app only)
├── schemas.py          # shape validation at the edge (Ninja Schema / Pydantic)
├── views.py             # thin: parse, call service, serialize, return
├── tasks.py              # one-line delegations to services
├── admin.py
└── tests/
```

`apps/api/keel/widgets/` is the reference implementation of this shape —
it is also the file set that `init` deletes, since it exists to
demonstrate the pattern rather than to ship.

Where business logic lives is not per-app discretion: **writes go through
`services.py`, reads go through `selectors.py`**, always, per invariant 1.

---

## Generators (Phase 19, ADR 0004)

`packages/cli` (`pnpm gen ...`) is the primary way a resource, permission,
job, transactional email, or e2e ship gate gets added — see CLAUDE.md's
generator catalogue for the full command list and the `/new-resource`
etc. slash commands that drive the judgement work each generator
deliberately leaves at a marked insertion point. `templates/` holds the
generators' source material as real, lintable Python and TypeScript (no
template-engine syntax); `pnpm gen resource` and `pnpm gen readonly-resource`
render it into a new app under `apps/api/keel/`, and `--ui` renders
`templates/ui` into the matching Next.js route group.

`apps/api/keel/widgets/` and `apps/web/app/(app)/app/[org]/widgets/` are
not hand-maintained reference code — they are a committed **render** of
`templates/resource` and `templates/ui`, held in place the same way
`packages/api-client/src/generated` is: improve the template, regenerate,
commit the diff. Three CI jobs in `.github/workflows/generators.yml` make
this an enforced property rather than a convention:

- **`templates-lint`** — ruff-checks and ruff-formats everything under
  `templates/` and fails if any template-engine file extension
  (`.hbs`, `.eta`, `.j2`, …) shows up, proving the templates are real
  source the repo's own linter reads.
- **`reference-slice-is-a-render`** — re-runs `pnpm gen resource Widget
--force --ui` in place and fails on any diff against what's committed
  under `apps/api/keel/widgets` and the widgets frontend route.
- **`generated-slice-passes-the-invariants`** — generates a throwaway
  resource, readonly-resource, permission, and email into the CI checkout
  and runs the full invariant suite (`lint-imports`,
  `check_permission_lint.py`, `makemigrations --check`, ruff, mypy,
  `pytest` including the tenant-isolation and permission-guard
  meta-tests) against it, so a generator regression is caught before it
  reaches a downstream project.

None of this is path-filtered — a change to `keel/core/authz.py` or the
permission registry shape can break every future generated slice without
touching `templates/` or `packages/cli/` at all, so `generators.yml` runs
on every push and PR like `ci.yml` does.

---

## Type synchronisation pipeline

```
Django Ninja (native OpenAPI, keel/core/api.py)  ──▶  OpenAPI (/api/v1/openapi.json)
                                            │
allauth headless                 ──▶  OpenAPI (/_allauth/openapi.json)
                                            │
                                            ▼
                          scripts/merge_openapi.py
                        (deterministic merge, sort_keys=True)
                                            │
                                            ▼
                              openapi.merged.json  (repo root)
                                            │
                                            ▼
                      packages/api-client (orval.config.ts)
                                            │
                                            ▼
                          packages/api-client/src/generated
                                (never hand-edited)
                                            │
                                            ▼
                                  apps/web (41 call sites)
```

CI's `contracts` job re-runs the merge and regenerates the client, failing
the build on any diff against what is checked in — this is what makes
"the generated client is never stale" an enforced property rather than a
hope.

**ADR 0001** (`docs/adr/0001-django-ninja-over-drf.md`) replaced
drf-spectacular's half of this diagram with Django Ninja's native OpenAPI
generation in Phase 10. The merge step, `openapi.merged.json`, and
everything downstream of it survived unchanged — only the left-hand
source of the Django-side spec moved.

---

## See also

- `docs/auth-flow.md` — the request-level picture of signup, login,
  session refresh, and CSRF that this document does not repeat.
- `docs/diagrams/system.md` — the deployed-system diagram (hosts, Django,
  Postgres, Redis, Celery, Stripe, storage).
- `docs/auth-client-contract.md` — the wire-level contract (cookies,
  headers, response envelopes, 401/403/409) for allauth headless.
- `keel-prd.md` §4 — the source these invariants are drawn from, and the
  place to look if this file and the code ever disagree.
- `docs/adr/0004-generators-as-the-agent-capability-surface.md` — why the
  generator CLI exists and what it deliberately leaves to judgement.
