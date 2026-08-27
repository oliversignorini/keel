# Keel — Django + Next.js SaaS Template

**Product Requirements Document**
Version 1.4 · 27 August 2026
Owner: Oliver Signorini

> **Keel** — the structural backbone a ship is built on; everything else attaches to it. Rename freely; the init script handles it.

### Revision note — v1.1

v1.0 was written before the first instantiation was chosen. Brein AI is that instantiation, and reading the two documents against each other surfaced places where Keel's shape and a real project's shape disagreed. Every change below traces to a concrete conflict rather than to a feature a template "should" have.

| # | Change | Driver |
|---|---|---|
| 1 | An optional pure `domain/` layer sits beneath `services.py`, with an import-linter contract | Keel's two-layer rule contradicted Brein's three-layer rule; a project cannot obey both |
| 2 | `has_perm` returns a `Decision`, not a bool | Boolean codes cannot express workflow-state guards ("drafts not approved") |
| 3 | The credit ledger replaces `UsageRecord` as the metered-billing primitive | A usage *record* is written after work; a *hold* is placed before it. Different primitive |
| 4 | Seat sync to Stripe moves behind a flag | Single-tenant-per-user projects run dead code that can still break |
| 5 | The task shim is scoped to single-step work; multi-step jobs use Celery directly | The shim was a wall the first project punched through on day one |
| 6 | New Phase 5.5 — `Job`/`JobStep`, SSE, job tray | Long-running work is the anticipated Tier 2 extension and has two deployment footguns worth proving at template level |
| 7 | Every viewset declares `organization_scoped` or a justification string | Global, non-tenant tables are legitimate; a silent exemption list is where leaks hide |
| 8 | The tenant noun is an `init` prompt | `Organization` → `Workspace` is a migration, a client regen and a permission-code rename |
| 9 | Third-party OAuth `Connection` named as an extension point | Login-with-Google and connect-your-Gmail are different flows with different scopes and lifecycles |
| 10 | Per-directory coverage gates replace a single global threshold | A global 80% fights a 100% requirement on one directory |
| 11 | `init` can delete the marketing route group; the demo slice can be kept as reference | Not every project is SEO-coupled, and a nine-month build wants the canonical pattern on hand |

### Revision note — v1.2

v1.1 was read end to end against an implementation plan. Nine things did not survive that reading: four were unsatisfiable as written, three named a mechanism the document never specified, and two were internal contradictions. None of them are new features. Every change below closes a gap that would otherwise have been closed differently by whoever hit it first.

| # | Change | Driver |
|---|---|---|
| 1 | `Decision`, the `Guard` protocol and the registry object move to `keel/core/authz.py`; `organizations/permissions.py` populates the registry and re-exports `has_perm` | Phase 1's `OrgScopedViewSet` cannot import from a Phase 3 app. The Phase 1 acceptance criteria were unsatisfiable as written |
| 2 | `Job` and `JobStep` land as schema in the baseline migration; Phase 5.5 adds behaviour only | `CreditLedgerEntry.job` is a Phase 4 foreign key to a Phase 5.5 model |
| 3 | The audit "service registry" is specified: an `@audited(action)` decorator in `keel/core` | Phase 8 asserted a meta-test over a registry that appears nowhere else in the document |
| 4 | Per-directory coverage is a `[tool.keel.coverage]` table read by `scripts/check_coverage.py`, not a `pyproject.toml` feature | pytest-cov has no per-directory threshold. The criterion named a mechanism that does not exist |
| 5 | The cross-tenant meta-test's mechanism is specified: scoped viewsets declare a `test_factory` | "Walks the router" is not implementable without a per-viewset source of fixtures |
| 6 | `uuid-utils` added to the backend manifest | `uuid.uuid7` is Python 3.14+; the version floor is 3.12 |
| 7 | SSE is served by a dedicated ASGI service, named in the deployment topology and in `railway.json` | Phase 5.5 required an async worker that no deployment artefact described |
| 8 | `<FileUpload>` added to the component inventory | Named as a Phase 5 deliverable, absent from §5 |
| 9 | Build order is chunked explicitly: Phases 0–4, sign-off, then 5–9 | §2 said build 0–4 and stop; §3 said 0–9 were all must-have |

### Revision note — v1.3

v1.2 was written before any of it was built. Phases 0 through 8 have now been implemented and verified, and this revision records what contact with the code changed. One item is a deliberate operator decision; the rest are things the document got wrong or left out, discovered by building it.

| # | Change | Driver |
|---|---|---|
| 1 | **The app shell moves to its own subdomain.** `app.acme.com/{org}` rather than `acme.com/app/{org}`, via a host-based Next middleware rewrite | Operator decision. The marketing site and the app are different products with different audiences, and a shared path prefix made that boundary a routing detail rather than a deployment one |
| 2 | Dev uses `lvh.me`, not `app.localhost` | The session cookie must be shared between the web and API origins. Browsers special-case `localhost` and handle a `Domain=.localhost` attribute inconsistently, so `app.localhost` would authenticate in production and fail in dev — the worst failure shape available |
| 3 | `KEEL_APP_DOMAIN` names the app's own host, not the registrable domain | Otherwise the Phase 2 cookie-domain startup check is satisfied by domain equality and never exercises its subdomain branch — a guard that silently stops guarding |
| 4 | `keel/jobs/` and `keel/connections/` added to the app list | The §4 layout had nowhere to put `Job`, `JobStep`, `FailedTask` or `Connection`, all of which are in the data model |
| 5 | `packages/emails/` named as a build-time dependency of the API test suite | react-email templates render to HTML at build. The rendered files are a build artefact, so a fresh clone and CI both start without them, and every allauth flow that sends mail fails several frames deep with an unrelated-looking 500 |
| 6 | Settings read `apps/api/.env` and fall back to the repository root | `.env.example` sits at the root, so copying it there is the obvious move, and Django's `BASE_DIR` is `apps/api`. The symptom was a `DisallowedHost` 400 with settings that looked correct on disk |
| 7 | The tenant URL segment is recorded as `organizations`, not `orgs` | The implementation used the longer form throughout. Named here as a known deviation rather than left as a silent disagreement between spec and code; see "Outstanding" below |

**Outstanding at v1.3.** Three items are known and deferred rather than done: the `organizations` → `orgs` URL rename, a cursor envelope on `GET /api/v1/plans/` (it returns a bare array, against the §7 convention that all collections are cursor-paginated), and wiring `e2e/auth-flows.spec.ts` into CI — it needs the live API and Mailpit as service containers, and only the accessibility spec runs today. Phase 9 is not built.

### Revision note — v1.4

v1.3 recorded what building Phases 0–8 taught. v1.4 records two decisions taken after a full review of the repository against the project's direction — see `docs/review-2026-08.md` for the review itself and `docs/adr/0001-django-ninja-over-drf.md` for the first decision's reasoning. Neither changes what Keel is; both change how the rest of it gets built.

| # | Change | Driver |
|---|---|---|
| 1 | **The API layer moves from DRF to Django Ninja.** §2's selected stack no longer names DRF. Django remains the app, auth, ORM, admin and jobs authority; Ninja is the typed API layer | DRF arrived with the stack in §2 and was never argued for. Pydantic-native schemas remove the serializer/type duplication in a template whose central claim is that the client is generated and drift is a build error. The migration cost — 19 viewsets, the invariant meta-tests, the cursor paginator, the OpenAPI pipeline — is recorded in ADR 0001, along with the case against |
| 2 | **Phases 9 onward are renumbered into one execution sequence.** §8's "Phase 9 — Template mechanics" is now **Phase 17**; its content is unchanged | `init` rewrites every file in the repository. Running it before the Ninja migration, the auth BFF, storage and the hardening pass means writing its rewrite rules against a structure that is about to change |

**The new sequence.** 9 Release credibility · 10 DRF → Ninja · 11 Auth BFF hardening · 12 Railway and Postgres baseline · 13 Document storage · 14 Billing and credits polish · 15 Jobs and audit foundations · 16 Production hardening · 17 Template mechanics (`init`, this document's §8 Phase 9) · 18 Portfolio polish and v1.0. Each has a plan file at `docs/plans/phase-N.md` carrying the boundary, tasks and acceptance criteria.

**Outstanding at v1.3, now owned.** The `organizations` → `orgs` rename and the cursor envelope on `GET /api/v1/plans/` are folded into Phase 10.C, which already sweeps every route and every frontend call site. Wiring `e2e/auth-flows.spec.ts` into CI is Phase 9.C.

---

## 1. Project Overview

### Executive summary

Keel is a reusable SaaS boilerplate: a Django 6 API and a Next.js 15 client in one monorepo, with the six load-bearing surfaces every B2B SaaS needs already built — authentication, multi-tenant organisations with granular permissions, Stripe subscription billing, background jobs, a marketing site with an MDX blog, and an application shell. It is instantiated once per project via a GitHub template plus an `init` script, and is deliberately shaped so Claude Code can extend it without architectural drift.

The user is one person: Oliver, building client and personal SaaS products, directing Claude Code rather than reading every diff. That single fact drives most of the design decisions in this document. Where there is a choice between a clever abstraction and an obvious one, the obvious one wins, because legibility is the primary defence against drift when the operator reviews outcomes rather than lines.

This is not a product with users to acquire. Its success is measured in build time saved and in how rarely the architecture has to be renegotiated after instantiation.

### Problem statement

Every new SaaS project re-solves the same problems, badly and slightly differently. Auth takes days to wire properly with social login, verification and MFA. Multi-tenancy gets bolted on after the first customer asks for a teammate, at which point every query needs an `org_id` retrofit. Stripe webhooks get written without idempotency and cause double-charges. Permissions accrete across route guards, UI conditionals and view methods until nobody can answer "who can cancel the subscription?" without reading three files.

Existing options don't fit. The mature open-source Django SaaS starters are HTMX-based and assume a server-rendered frontend. SaaS Pegasus is the most complete Django option and is worth a licence purely to read its team/membership model, but it isn't Next.js-first. The Next.js SaaS boilerplates put the entire backend in TypeScript, which forfeits Django's ORM, admin and Python-native data tier — the exact reasons the stack was chosen.

### Success metrics

| Metric | Target |
|---|---|
| Time from `init` to a deployed, authenticated, billable app | Under 4 hours |
| Architectural questions needing a decision after instantiation | Zero for auth, tenancy, billing, permissions, async |
| Claude Code sessions that introduce a permission check outside `permissions.py` | Zero (enforced by CI meta-test) |
| Backend test coverage at instantiation | Per-directory gates met (§4, invariant 7), 100% on the permission registry |
| Monthly infrastructure cost for a pre-revenue project | Under AUD $40 |
| Demo resource deleted and replaced with real domain within first session | Yes |

---

## 2. Stack Selection

The stack was specified by the operator rather than derived, so this section records the reasoning that would have produced it, the runner-up, and the tension — so the decision can be revisited honestly later.

### The eight answers

| | Question | Answer |
|---|---|---|
| **A** | Authorization shape | **Contextual.** Organisation membership, granular named permissions, roles as editable presets. Not "user owns row". |
| **B** | Async work | **Yes.** Stripe webhook fan-out, transactional email, dunning, trial expiry, invitation expiry, usage rollups, scheduled jobs. |
| **C** | Admin surface | **Split.** Django admin, staff-only, internal. A separate customer-facing organisation settings UI in Next.js. Audit trail and impersonation required. |
| **D** | Client surfaces | **Web only.** PWA-capable but not a target. Mobile is explicitly out of scope, with the JWT token strategy left configured-but-off as the seam. |
| **E** | UI shape | **App-like.** Rich client state, optimistic updates, command palette, data tables. Not document-like. |
| **F** | SEO coupling | **Yes.** Marketing site, pricing page and MDX blog share the app's domain and must be indexed. |
| **G** | AI/data tier | **Tier 1 at template level** (no AI in the box), with Tier 2 as the anticipated per-project extension — layout parsing, dataframes, embeddings. Python-native backend is the point. |
| **H** | Verifiability | **Directs rather than reviews.** The operator makes architectural decisions and reviews outcomes; Claude Code writes the code. |

### Should this be built at all?

Yes, but the honest version of the question is *should this be built as a template*, and the answer is only yes because the operator ships more than one of these per year. A single SaaS project should not pay the cost of generalisation. The template earns out on the second instantiation and is a loss on the first.

The failure mode to watch: template features that exist because a template "should have them" rather than because a real project needed them. Every phase below is traceable to a concrete need.

### Sequencing the first instantiation

The template is a loss on the first instantiation by construction. If the first project also needs primitives Keel does not ship — long-running jobs, a credit ledger, provider ports, a pure domain layer — the loss is larger than normal, because those get built twice: speculatively here, then properly there.

The recommended sequence is therefore **not** "finish Keel, then start the project."

1. **Build Phases 0–4 in full.** Repository, Django foundation, auth, organisations and permissions, billing. These are the phases a project uses close to unchanged, and they are the ones nobody wants to write twice.
2. **Start the first project on that.** Phases 5–9 are written below and should be treated as specified-but-not-yet-built.
3. **Backport.** When the project forces the real shape of jobs, emails, the app shell, or a slash command, implement it there first and lift it into Keel once it has survived contact.

This is the same anti-speculation principle applied to the template's own schedule. The risk it accepts is that backporting is a refactor that never happens; the mitigation is that Phases 5–9 already exist as written specifications, so lifting is a port rather than a design.

### Selected stack

**Django 6 + DRF API, separate Next.js 15 client. Two deploys, chosen deliberately.**

This is the row matched by A=contextual, B=yes, D=app-like, F=SEO-coupled. Answer **H** is the modifier that mattered most: when the operator directs rather than reads every line, the framework's refusal to allow the wrong shape is the main defence against drift. Django's app boundaries, migrations, and admin do that work.

### Runner-up, and why it lost

**Laravel + Filament.** It won on the table — it is the top matching row, and it would have delivered queues, scheduler, policies, tenancy, both admin panels and billing as first-party features, collapsing Phases 3 through 5 almost entirely. Filament alone would have removed the customer-facing settings UI from scope.

It lost on two things, neither architectural:

1. The operator does not write PHP and would be directing Claude Code in an unfamiliar language, which removes the ability to sanity-check outcomes — precisely the check that answer H makes load-bearing.
2. The anticipated per-project extension is Tier 2 data and AI work, which is Python. Laravel would force a second language and a second service for exactly the work most likely to be added.

**Record the tension:** Keel spends roughly three phases (3, 4, 5) building what Laravel + Filament ships. That is a real, quantifiable cost — call it 40–60% of the template's build effort. It is paid once, at template level rather than per project, which is what makes it tolerable. If a future project is document-shaped, has no Python requirement, and needs a full admin fast, the correct answer is Laravel and this template should not be forced onto it.

**Second runner-up: Next.js + Supabase.** Lost immediately. A=contextual plus B=yes puts it in the rightmost, highest-risk column of the invariants table — the configuration where the stack does the least to enforce placement and where authorization splits between server guards and row-level policies. It is the right answer for ownership-shaped apps with no async, which describes none of the intended projects.

### Client surface

Web only, rendered by Next.js on Vercel. Resolved independently of the service stack. If a mobile client is ever needed, the Django API serves an Expo app perfectly well and the auth layer already supports it — allauth's headless API uses an `X-Session-Token` header specifically for non-browser contexts. That seam is configured and disabled, not designed-for.

### Where business logic lives

**Domain logic lives in `services.py` within each Django app.** Views, serializers, Celery tasks, Django admin, management commands, signals and the Next.js client are all forbidden from holding business rules. A view that contains an `if` about business state is a bug, not a style preference.

Read queries live in `selectors.py`. The distinction is enforced by convention and by code review prompts in `CLAUDE.md`: services mutate and return, selectors query and return.

---

## 3. User Stories & Requirements

### By role

**Anonymous visitor**
- Read the marketing site and blog, indexed by search engines
- Compare plans on a pricing page with monthly/annual toggle
- Sign up with email and password, or with Google
- Accept an invitation to an existing organisation from an email link

**Organisation Owner**
- Create an organisation on first signup, and switch between organisations
- Invite members by email, assign a role, revoke a pending invitation
- Change a member's role, remove a member
- Create custom roles from the permission registry (when custom roles are enabled for the project)
- Start a subscription, change plan, update payment method, cancel
- View invoices and manage billing through the Stripe Customer Portal
- View the organisation audit log
- Transfer ownership, delete the organisation

**Organisation Admin**
- Everything an Owner can do except delete the organisation and transfer ownership

**Organisation Member**
- View the organisation and its members
- Full CRUD on the project's domain resources, subject to permissions
- Manage their own profile, password, MFA devices, and active sessions

**Staff (internal)**
- Access Django admin for reference data and support
- Impersonate a user, with the session recorded in the audit log and a persistent banner shown in the UI

### Non-functional requirements

**Performance**
- API p95 under 300ms for list endpoints at 10k rows per organisation
- Marketing pages: LCP under 2.0s on 4G, Core Web Vitals in "good"
- The demo resource list page must remain fast with 50k rows via cursor pagination

**Security**
- HttpOnly, Secure, SameSite=Lax session cookies scoped to the registrable domain
- CSRF enforced on all unsafe methods
- Rate limiting on auth endpoints (allauth built-in) and on the API generally
- Stripe webhook signature verification, mandatory
- No secret in the repository; `.env.example` documents every variable
- Every organisation-scoped query filtered by organisation at the queryset layer, verified by a cross-tenant meta-test

**Accessibility**
- WCAG 2.1 AA
- Keyboard navigation throughout, visible focus rings, command palette as a first-class navigation path
- `prefers-reduced-motion` respected

**Scalability**
- Single Postgres, row-level `organization_id` scoping. No schema-per-tenant.
- Horizontal scaling of API and worker processes independently
- Redis for cache, Celery broker, and rate limit counters

### Prioritisation

**Must-have (template v1.x):** Phases 0–9 below, including 5.5. A template with a gap in auth, tenancy or billing is not a template.

**Built in two chunks, and the gate between them is real.** §2 argues for building Phases 0–4 and then starting the first project on them; this section calls all ten phases must-have. Both are true and v1.1 left them sitting next to each other unreconciled. The resolution: 0–4 is one delivery, signed off end to end — a running, authenticated, billable app with tenancy and permissions enforced — before 5–9 is planned in any detail. That gate exists because Phases 5 through 9 are the ones §2 predicts will be reshaped by contact with a real project, and planning them against an imagined project is the specific failure this document keeps warning about. They remain must-have for the template. They are not must-have for the first sign-off.

**Deliberately out of scope:** bidirectional realtime/WebSockets, mobile/Expo client, i18n, AI features themselves, SSO/SAML/SCIM, and a customer-facing analytics dashboard. Each has a named extension point in §9.

**No longer out of scope, and why.** v1.0 deferred metered billing to a `UsageRecord` table and long-running work to "add Channels later." Both were wrong in the same way: they named a seam that did not fit the thing it was supposed to admit. Credits need a reservation before the work, not a record after it, and a job system needs rows, resumption and streaming rather than a socket. Both now ship — credits behind a flag, jobs as Phase 5.5.

---

## 4. Technical Architecture

### System architecture

```
                    ┌─────────────────────────────┐
   acme.com ───────▶│  Next.js 15 (App Router)    │
   (marketing+app)  │  Vercel                     │
                    │  ┌──────────┬─────────────┐ │
                    │  │(marketing)│   (app)    │ │
                    │  │ MDX blog  │  dashboard │ │
                    │  └──────────┴─────────────┘ │
                    └──────────────┬──────────────┘
                                   │ fetch, credentials: include
                                   │ Cookie: sessionid (domain=.acme.com)
                                   ▼
   api.acme.com ────────▶┌─────────────────────────┐
                         │  Django 6 + DRF  (sync) │◀──── Stripe webhooks
                         │  Railway · gunicorn     │
                         │  request/response only  │
                         └────┬──────────┬─────────┘
                              │          │
   api.acme.com/…/stream ────▶│  ┌───────┴──────────────┐
                              │  │ Django ASGI (async)  │   same image,
                              │  │ Railway · uvicorn    │   separate service.
                              │  │ SSE only. Proxy      │   Phase 5.5.
                              │  │ buffering OFF.       │
                              │  └───────┬──────────────┘
                              │          │
              ┌───────────────┘          └──────────────┐
              ▼                                         ▼
     ┌─────────────────┐                       ┌─────────────────┐
     │  Postgres 17    │                       │   Redis 7       │
     │  (Railway mgd)  │                       │  broker+cache   │
     └─────────────────┘                       └────────┬────────┘
                                                        │
                                          ┌─────────────┴─────────────┐
                                          ▼                           ▼
                                 ┌─────────────────┐        ┌─────────────────┐
                                 │  Celery worker  │        │   Celery beat   │
                                 │  (same image)   │        │   (scheduler)   │
                                 └─────────────────┘        └─────────────────┘

   External:  Stripe · Resend (email) · Cloudflare R2 (files) · Sentry · PostHog

   The SSE endpoint is a separate Railway service running the same image under
   uvicorn, on the same hostname via path routing. It is separate because a
   held-open connection under the sync worker pool exhausts it at a user count
   far below what request/response load testing suggests, and because the
   proxy configuration that stops it buffering `text/event-stream` should not
   be applied to the API's ordinary traffic. `railway.json` declares both.
```

### Repository layout

```
keel/
├── apps/
│   ├── api/                       # Django 6
│   └── web/                       # Next.js 15
├── packages/
│   ├── api-client/                # generated — never hand-edited
│   ├── ui/                        # shadcn components + theme tokens
│   ├── eslint-config/
│   └── tsconfig/
├── infra/
│   ├── compose.dev.yml            # postgres, redis, mailpit only
│   ├── compose.prod.yml           # full stack, prod parity
│   ├── Caddyfile                  # self-host path
│   └── railway.json
├── scripts/
│   └── init.ts                    # instantiation
├── docs/
│   ├── architecture.md            # the seven invariants, verbatim
│   ├── deploy-railway.md
│   ├── deploy-selfhost.md
│   └── brand-pass.md
├── .github/workflows/ci.yml
├── .claude/
│   ├── commands/                  # slash commands
│   └── skills/
├── CLAUDE.md
├── turbo.json
└── pnpm-workspace.yaml
```

### Django app layout

Every domain app has the same seven files. This uniformity is the point — Claude Code should never have to guess where something goes.

```
apps/api/
├── config/
│   ├── settings/{base,dev,prod,test}.py
│   ├── urls.py
│   ├── celery.py
│   └── asgi.py
├── keel/
│   ├── domain/                    # OPTIONAL pure layer — no ORM, no HTTP,
│   │                              # no Celery. Enforced by import-linter
│   ├── core/                      # base models, mixins, exceptions,
│   │                              # pagination, task shim, org scoping
│   ├── accounts/                  # User, profile, allauth glue
│   ├── organizations/             # Org, Membership, Role, Invitation,
│   │                              # PERMISSION REGISTRY
│   ├── billing/                   # Plan, Price, Subscription, entitlements,
│   │                              # Stripe webhook handling
│   ├── audit/                     # AuditLog, impersonation
│   ├── notifications/             # email dispatch
│   ├── files/                     # presigned R2 uploads
│   ├── jobs/                      # Job, JobStep, FailedTask (Phase 5.5)
│   ├── connections/               # third-party OAuth Connection
│   └── widgets/                   # DEMO RESOURCE — `init` deletes this
└── tests/

# Per-app structure (non-negotiable):
widgets/
├── models.py         # data shape only
├── services.py       # ← ORM, transactions, side effects, all writes
│                     #   may call keel/domain/; never reimplements it
├── selectors.py      # ← all reads
├── permissions.py    # ← required permission codes for each action
├── serializers.py    # ← shape validation at the edge
├── views.py          # ← THIN. parse, call service, serialize, return
├── tasks.py          # ← one-line delegations to services
├── admin.py
└── tests/
```

### Architecture Invariants

All seven, stated plainly. `docs/architecture.md` carries these verbatim and `CLAUDE.md` references them.

**1. Where does domain logic live?**
Domain logic lives in `services.py` and `selectors.py` inside each Django app. Views, serializers, Celery tasks, Django admin, management commands, database triggers, and the Next.js client are forbidden from holding business rules. A Celery task body is a single call into a service.

**The optional third layer.** Some projects have rules worth isolating from Django entirely — scoring, pricing, rule engines, ledger arithmetic, anything that is a pure function over values and deserves exhaustive unit tests with the database switched off. Those live in `keel/domain/`, as pure Python: no ORM imports beyond type hints, no HTTP, no Celery, no settings access.

```
keel/domain/                # created only when a project needs it
  <rules>.py                # pure functions over dataclasses
  invariants.py             # validation shape validation cannot express
```

The relationship is one-directional and non-negotiable: **`services.py` may call `domain/`; `domain/` may never call anything.** Services own the ORM, the transaction, and the side effects; `domain/` owns the arithmetic and the rules.

`import-linter` ships in the template with a contract covering `keel/domain/`. The contract is inert while the directory is empty and becomes a CI gate the moment anything is added to it, so a project opts in by creating a file rather than by editing configuration. Projects with no pure rules never create the directory and never think about it again.

This is a genuine fork in how a project is written, and `CLAUDE.md` records which side of it the project is on. A two-layer project that lets rules accrete in `services.py` is fine. A three-layer project that lets ORM queries leak into `domain/` is broken, and CI says so.

**2. Where is authorization expressed?**
Authorization is expressed only in `organizations/permissions.py`, as a registry of named permission codes plus a single `has_perm(user, organization, code, subject=None)` function. DRF viewsets declare `required_permissions` and the `HasOrgPermission` permission class calls that one function. Permission logic must not appear in views, serializers, querysets, templates, or the client. The client receives the user's permission list from `/me` and uses it **only to decide what to render** — never as enforcement.

**`has_perm` returns a `Decision`, not a bool.**

```python
@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str | None = None          # machine-readable, e.g. "insufficient_role"
    details: dict | None = None        # what the caller needs to fix it

    @classmethod
    def allow(cls) -> "Decision": ...
    @classmethod
    def deny(cls, reason: str, details: dict | None = None) -> "Decision": ...
```

**Where the type lives, and why it is not in this file.** `Decision`, the `Guard` protocol and the registry object live in `keel/core/authz.py`. The permission *codes* and their guard implementations live in `organizations/permissions.py`, which registers them at app-ready time and re-exports `has_perm` so call sites read exactly as this document describes them.

The split exists because `keel/core` may not import from `keel/organizations`. `OrgScopedViewSet` and `HasOrgPermission` are core base classes built in Phase 1; the organisations app arrives in Phase 3. A base class that imports its own dependent is a circular import at best and an ordering trap at worst, and Phase 1's acceptance criteria — a viewset that raises at import when it declares no `required_permissions` — cannot be met by code that does not yet exist.

The invariant is unchanged. Authorization is *expressed* in one file, and that file is `organizations/permissions.py`. Only the vocabulary it is expressed in lives in core, and `keel/core/authz.py` contains no permission code, no role, and no rule — a registry, a protocol and a dataclass, and nothing that answers a question about a user.

A bool answers "may I?" and nothing else. Three things need more than that:

- **403 bodies become debuggable.** `reason` maps straight into the error envelope's `code`, so a denial says `insufficient_role` rather than a blank wall, and support can answer "why can't I click this?" from a log line.
- **Workflow state fits.** Real products gate on more than role — an action may require that a linked resource is approved, that a connection is healthy, that a period is open. `Decision.deny("drafts_not_approved", details={"ids": [...]})` expresses that; `False` does not.
- **The seam has one shape.** Without it, workflow guards end up as `if` statements in services, which is a permission check outside `permissions.py` by any reading of this invariant.

**Codes and guards are the same registry.** A simple code is a guard whose implementation only looks at the role. A guard that inspects a subject is registered the same way and declared on the viewset the same way. The distinction is implementation depth, not category.

**Services may call guards; services may never reimplement them.** A service enforcing a rule that authorization already owns is a duplicate source of truth, and the two will diverge. If a service needs a check, it calls `has_perm` and raises on denial.

Every registered guard has a unit test with one allow case and one deny case. A CI meta-test walks the registry and fails if any entry lacks both. Deny tests assert the `reason`, not merely that access was refused — a guard that denies for the wrong reason passes a boolean test and fails a user.

**3. What is the transaction boundary?**
One `transaction.atomic()` per service function, opened inside the service, never in the view. Multi-step operations that touch Stripe follow this order: mutate local state inside the transaction, then dispatch the external call via `transaction.on_commit()`. Nothing calls Stripe from inside an open transaction.

Webhook processing is the mirror image: record the `StripeEvent` row first for idempotency, then apply the state change in an atomic block. Replaying an event is a no-op by construction, and there is a test that replays every handled event type twice.

**4. How do schema changes happen?**
Django migrations, in version control, reviewed, reversible where practical. CI fails on missing migrations (`makemigrations --check --dry-run`). **No dashboard, console, or admin interface may alter schema.** Railway's database UI is for inspection only.

**5. Where does async work run?**
Celery workers with a Redis broker, plus Celery beat for scheduling, running from the same Docker image as the API.

**Two tiers, and the boundary between them is explicit.**

*Tier 1 — fire-and-forget.* Single-step work that either succeeds or retries: send an email, sync a Stripe object, run a nightly rollup. Declared through a thin shim in `keel/core/tasks.py` that mirrors Django 6's `django.tasks` surface (`@task` / `.enqueue()`) while executing on Celery — roughly twenty lines, bought so this class of work is portable without touching call sites. Every template-shipped task is Tier 1.

*Tier 2 — multi-step jobs.* Work that runs for minutes, commits intermediate results, resumes after a crash, streams progress, and can end in partial success. **This uses Celery directly** — chains, per-queue routing, custom task base classes, semaphores. Do not extend the shim to cover it.

The reason for saying this plainly: the shim's value is portability across a queue backend, and that value is only real for work whose entire interface is "run this later." The moment a job needs step-level commits, cost-profile queues, or per-tenant concurrency fairness, it needs Celery's actual surface, and an abstraction that hides it is a wall to be punched through rather than a seam. Phase 5.5 builds the Tier 2 primitive properly; the shim stays small and stays honest about what it covers.

*Note on the shim's existence:* Django 6.0 shipped `django.tasks` as a standard API but no production worker, scheduler, retry policy, or durable backend. Celery remains the answer for anything with periodic jobs, which this template has. `django-tasks-celery` exists as an official-shaped bridge but is 0.1.x beta and is not depended on.

**Queues.** Four, routed by cost profile rather than by domain: `default`, `email`, `external` (third-party API calls, rate-limit sensitive), `scheduled`. Separation exists so a backlog in one profile cannot starve another — a hundred queued enrichment calls must not delay a password-reset email. Projects add queues; they do not collapse these.

Retry policy: exponential backoff with jitter, 5 attempts, then dead-letter to a `FailedTask` row plus a Sentry event, re-drivable from Django admin. Every task is idempotent by design and every task takes IDs, never model instances.

Scheduled jobs: Stripe plan sync (daily), invitation expiry (hourly), trial-ending notices (daily), dunning check (daily), audit log retention (weekly), expired session cleanup (daily).

**6. What is the validation boundary?**
Two layers, both mandatory. DRF serializers validate shape at the HTTP edge and reject malformed input with 400. Services enforce invariants and raise typed domain exceptions that map to 409 or 422. Client-side Zod validation exists for UX responsiveness only and is never enforcement — the Zod schemas are generated from the same OpenAPI spec, so they cannot drift from the server's shape contract.

**7. What gets tested, at which layer, and how is that enforced?**

**Coverage is gated per directory, not by a single global number.** One threshold across the whole backend is a number that gets negotiated downward: a directory that must be at 100% is dragged below it by a mock-heavy adapter package, and the only way to keep CI green is to lower the bar for everything. Per-directory gates let each layer carry the obligation it actually has.

*The mechanism, stated because pytest-cov does not have one.* `--cov-fail-under` takes a single number over the whole run, and no per-path variant exists. So the thresholds are a `[tool.keel.coverage]` table in `pyproject.toml` — a mapping of path glob to required percentage — read by `scripts/check_coverage.py`, which runs after pytest against `coverage.json` and exits non-zero naming every path that missed, with its actual and required figure. A path matched by no glob is reported and does not fail the build; a glob matching no path *does* fail, because that is a directory that was renamed or deleted while its obligation was left behind.

| Layer | Obligation | CI gate |
|---|---|---|
| Permission registry | Allow + deny test for every registered guard, deny asserting the `reason` | Meta-test fails on any uncovered guard |
| `keel/domain/` (if present) | Pure rules exhaustively tested | 100%, no exemptions |
| Tenant isolation | Cross-org access returns 404 for every org-scoped viewset | Meta-test walks the router (see below) |
| Services | Unit tests for each service function, including failure paths | 90% per `services.py` |
| Stripe webhooks | Every handled event type, replayed twice | Explicit test module, no coverage exemption |
| Credit ledger (if enabled) | Balance arithmetic and concurrent holds | 100% on `billing/credits.py` |
| Adapters / third-party clients | Conformance against recorded fixtures | 60% — deliberately low; these are thin and mock-heavy |
| API contract | OpenAPI spec regenerates without diff | CI fails if generated client is stale |
| Web units | Vitest on hooks and utilities | 70% coverage |
| E2E | Signup → org → invite → subscribe → CRUD | Playwright, must pass on every PR |

**Tenant scoping is declared, never inferred.** Not every table is tenant-scoped — reference data, shared caches, global taxonomies and internal ML artefacts are legitimately global, and a project will have some. The failure mode is that the cross-tenant meta-test hits the first global viewset, someone adds it to an exemption list, and the exemption list becomes the place leaks hide.

So every viewset must declare one of two things at class level, and the meta-test fails at import if neither is present:

```python
class WidgetViewSet(OrgScopedViewSet):
    organization_scoped = True          # tested for cross-org 404

class BrandViewSet(GlobalViewSet):
    organization_scoped = False
    GLOBAL_JUSTIFICATION = (
        "Enrichment is identical across tenants and expensive to recompute. "
        "Ids are never addressable from the public API; tenant-private "
        "relationships live on WorkspaceBrand."
    )
```

CI prints every `GLOBAL_JUSTIFICATION` in the test output. An exemption you have to write a paragraph for, and that appears in every CI run, is a decision. An entry in a list is not.

*How the meta-test gets its fixtures.* Walking the router yields viewset classes, not data, and a cross-tenant assertion needs a row in organisation A that a member of organisation B will fail to reach. So a scoped viewset declares its own source of rows:

```python
class WidgetViewSet(OrgScopedViewSet):
    organization_scoped = True
    test_factory = "keel.widgets.tests.factories.WidgetFactory"
```

The meta-test imports the factory by path, builds one instance in each of two organisations, and asserts that every detail route on the viewset returns 404 — not 403 — when requested by a member of the other. `test_factory` is required whenever `organization_scoped = True`; the import-time check that already rejects a missing `organization_scoped` rejects a missing factory on the same terms. The string path rather than the class keeps test code out of production imports.

Where a global table has a tenant-scoped companion (the private relationship, score, or annotation that belongs to one organisation), the global row's id must not be exposed by the public API — the companion's id is the addressable one. Enumeration across a shared table is the specific leak this prevents.

No business logic lives in the database — no stored procedures, no triggers, no row-level security. This is deliberate: it removes the database-layer testing obligation entirely, which is the layer most systematically under-tested. If a future project adds a trigger, that project inherits a database test suite as a numbered phase.

### Auth architecture

**django-allauth in headless mode owns identity.** Version 65.19+, `HEADLESS_ONLY = True`.

What it provides out of the box: email/password, email verification, password reset, social providers, MFA (TOTP and WebAuthn), a user-sessions app for listing and revoking active sessions, and built-in rate limiting. It also serves its own OpenAPI specification at `/_allauth/openapi.json`, which feeds the generated TypeScript client alongside the DRF spec.

`HEADLESS_FRONTEND_URLS` points verification and reset emails at Next.js routes rather than Django templates.

**Session transport: HttpOnly cookies, not JWT.** allauth's headless flow is inherently stateful — partially-authenticated states like "passed password, awaiting TOTP" live in the session. The browser client uses the cookie; the `X-Session-Token` header path exists for non-browser clients and stays unused.

**The domain constraint this imposes.** The API must sit on a subdomain of the app's registrable domain:

```
acme.com          → Next.js, the (marketing) and (auth) route groups
app.acme.com      → Next.js, the (app) route group        ← v1.3
api.acme.com      → Django, Railway, custom domain via CNAME
Cookie: Domain=.acme.com; HttpOnly; Secure; SameSite=Lax
```

All three are subdomains of one registrable domain, so the single session
cookie reaches all of them and the constraint above is unchanged by the
split. One Next.js deployment serves both route groups; a middleware
rewrite keyed on the `Host` header decides which.

**Local development uses `lvh.me`, not `localhost`.** `lvh.me` is a public
DNS name whose wildcard resolves to `127.0.0.1`, which makes it a real
registrable domain that a shared cookie can be scoped to:

```
lvh.me:3000       → marketing + auth
app.lvh.me:3000   → the app
api.lvh.me:8000   → Django
Cookie: Domain=.lvh.me
```

`app.localhost` is the obvious choice and the wrong one. Browsers
special-case `localhost` and handle a `Domain=.localhost` cookie attribute
inconsistently, so the app would authenticate correctly in production and
fail to authenticate in dev — a failure that appears only on the machine
you are least expecting it on. `lvh.me` depends on a third-party DNS record
and therefore fails offline; `docs/dev-setup.md` documents a hosts-file
fallback for that case.

**`KEEL_APP_DOMAIN` names the app's own host** (`app.acme.com`), not the
registrable domain. Set to the registrable domain instead, the startup
check below is satisfied by simple equality and never exercises the
subdomain branch that is the whole point of it.

Cross-registrable-domain cookies are third-party cookies and are blocked. This is not optional and is the first thing `init` prompts for.

**Preview deployments.** Vercel preview URLs on `*.vercel.app` break the cookie. Resolution: a wildcard preview domain `*.preview.acme.com` (requires Vercel Pro), with a staging API at `api.preview.acme.com`. `init` configures both.

Rejected alternatives, recorded so they are not relitigated:
- **Clerk** — good organisation model, but identity lives outside Django. Every `Organization` foreign key becomes a sync problem, and per-MAU pricing compounds across multiple projects.
- **Better Auth** — TypeScript-native, would put auth in Next.js while Django owns the data. Split-brain, and the API can no longer be the single enforcement point.
- **dj-rest-auth + simplejwt** — the previous default. allauth headless supersedes it and is more actively maintained.

### Tenancy and permissions

**The tenant noun is chosen at `init`.** The template is written in terms of *Organization*, but projects call this a Workspace, a Team, an Account or a Company, and the choice is not cosmetic — it appears in the model name, the URL segment, the permission-code prefix (`org.view`), the React route parameter, the components (`<OrgSwitcher>`), and the copy. Retrofitting it after the first migration means a schema change, a permission-code rename with a data migration over `Role.permissions`, a full client regeneration, and a sweep of the UI.

So `init` prompts for the noun and rewrites all six surfaces at once, before there is any history to migrate. The rest of this document says *organisation*; read it as whatever the project chose.

**Row-level scoping with the tenant in the URL path.**

```
/api/v1/orgs/{org_slug}/widgets/
/api/v1/orgs/{org_slug}/members/
/api/v1/orgs/{org_slug}/billing/subscription/
```

Path-scoped rather than header-scoped because the router can then enforce it: `OrgScopedViewSet` resolves the organisation, checks membership, and filters the queryset before any view code runs. A viewset that forgets to scope cannot exist, because scoping happens in the base class. It also maps cleanly to Next.js routes at `/app/[org]/…`.

**Permissions are named strings; roles are editable presets that map to sets of them.**

```python
# organizations/permissions.py — the single source of truth
class Perm:
    ORG_VIEW            = "org.view"
    ORG_UPDATE          = "org.update"
    ORG_DELETE          = "org.delete"
    ORG_TRANSFER        = "org.transfer"
    MEMBERS_VIEW        = "members.view"
    MEMBERS_INVITE      = "members.invite"
    MEMBERS_REMOVE      = "members.remove"
    MEMBERS_CHANGE_ROLE = "members.change_role"
    ROLES_MANAGE        = "roles.manage"
    BILLING_VIEW        = "billing.view"
    BILLING_MANAGE      = "billing.manage"
    AUDIT_VIEW          = "audit.view"
    # + one group per domain resource, added by /new-resource
```

Seeded presets: **Owner** holds every code. **Admin** holds everything except `org.delete` and `org.transfer`. **Member** holds the view codes plus resource CRUD. Custom roles are a per-project feature flag, off by default — the `Role` model and `roles.manage` permission exist from day one so enabling it is a settings change, not a migration.

Only permission codes are ever checked in code. Role names never appear in a conditional.

### Data model

```
User                    id(uuid) email(unique, USERNAME_FIELD) name avatar_url
                        is_staff is_active date_joined

Organization            id(uuid) name slug(unique) stripe_customer_id
                        created_by → User  created_at  deleted_at

Role                    id organization → Org (null = system preset)
                        name  permissions(jsonb: list[str])  is_preset

Membership              id organization → Org  user → User  role → Role
                        status(active|suspended)  joined_at
                        unique(organization, user)

Invitation              id organization → Org  email  role → Role
                        token(unique)  invited_by → User
                        expires_at  accepted_at  revoked_at

Plan                    id code(unique) name stripe_product_id
                        entitlements(jsonb)  is_active  sort_order

Price                   id plan → Plan  stripe_price_id(unique)
                        interval(month|year)  unit_amount  currency  is_active

Subscription            id organization → Org (one-to-one)
                        stripe_subscription_id(unique)  plan → Plan  price → Price
                        status  quantity  current_period_end
                        trial_end  cancel_at_period_end

StripeEvent             id(stripe event id, PK)  type  payload(jsonb)
                        received_at  processed_at  error

CreditLedgerEntry       id organization → Org  job → Job(null)
                        kind(grant|hold|consume|release|refund|adjustment)
                        amount(signed int)  reason  actor → User(null)
                        created_at        # append-only. never updated

CreditBalance           organization → Org (one-to-one, PK)
                        balance(int)  updated_at
                        # materialised SUM(amount). the ledger is the truth

Connection              id organization → Org  provider  external_account
                        access_token(encrypted)  refresh_token(encrypted)
                        scopes(array)  status(active|reauth_required|revoked)
                        connected_by → User  expires_at
                        unique(organization, provider, external_account)
                        # third-party OAuth. NOT allauth's SocialAccount

Job                     id organization → Org  type  status(queued|running|
                        succeeded|partial|failed)  requested_by → User
                        params(jsonb)  result_ref  error  idempotency_key
                        created_at  started_at  finished_at
                        # SCHEMA lands in the baseline migration (see below).
                        # Behaviour is Phase 5.5.

JobStep                 id job → Job  name  ordinal  status  output_ref
                        started_at  finished_at  error
                        # SCHEMA in the baseline. Behaviour is Phase 5.5.

FailedTask              id task_name  args(jsonb)  error  traceback
                        attempts  created_at  redriven_at

AuditLog                id organization → Org(null)  actor → User(null)
                        impersonator → User(null)  action  target_type
                        target_id  metadata(jsonb)  ip  user_agent  created_at

FileUpload              id organization → Org  uploader → User  key(unique)
                        content_type  size  status(pending|complete)  created_at

Widget                  id organization → Org  name  description  status
                        created_by → User  created_at  updated_at
                        # DEMO — the copy-paste pattern. init deletes it.
```

**The whole schema above lands in one baseline migration, before any feature work.** Models are cheap to write and expensive to reorder, and two of the relationships here cross a phase boundary in the wrong direction: `CreditLedgerEntry.job` is a Phase 4 column pointing at a Phase 5.5 table, and `AuditLog.impersonator` is a Phase 3 column that nothing reads until Phase 8. Building each phase's tables inside that phase means either a forward-declared foreign key, a nullable string that becomes a real relation later, or a migration in Phase 5.5 that alters a table Phase 4 has been writing to in production.

None of those are hard problems on their own. They are, together, the reason a template's migration history reads as an archaeology of its own build order rather than as a schema. So every table in this section is created once, in a single baseline, with its columns and constraints final. Phases add services, views, serializers, permissions and tests against tables that already exist. A phase that discovers it needs a column adds one, deliberately, and that migration is reviewed as a schema change rather than absorbed as scaffolding.

The practical consequence for parallel work: implementation branches inherit the baseline and do not generate migrations. One that does has either found a genuine gap in this section — which is worth knowing — or has drifted.

**Entitlements** live in `Plan.entitlements` as JSON:

```json
{
  "seats": 10,
  "widgets": 500,
  "features": ["api_access", "audit_log", "custom_roles"]
}
```

`GET /api/v1/me/` returns the user, their organisations, the current organisation's role, the resolved permission code list, and the resolved entitlements. That single endpoint is what the client renders from. Server-side, `@requires_entitlement("api_access")` gates features and `check_limit(org, "widgets")` gates quantities — both in `billing/services.py`, both raising typed exceptions.

### Credits — the metered-billing primitive

v1.0 named `UsageRecord` plus a nightly rollup as the seam for metered billing. That is the wrong primitive, and the difference is not academic.

A usage record is written **after** work happens. It answers "what did they consume last month?" and bills in arrears. That is correct when the marginal cost of a unit is cents and the customer is invoiced monthly.

Products with expensive units have to answer a different question: **may this operation start, and is the money already reserved?** A job that will spend three dollars with a third party must not begin against a balance two other browser tabs have already claimed. That needs a reservation placed before the work, settled after it, and released or refunded when the work ends short. A rollup cannot do it, and a mutable `Organization.credit_balance` integer double-spends under exactly the normal case — one user starting three jobs from three tabs.

So the template ships a ledger instead.

```python
class CreditLedgerEntry(models.Model):
    # Append-only. Never updated, never deleted.
    KIND = [
        ("grant",      "plan allowance or purchased top-up"),
        ("hold",       "negative, reserved at job creation"),
        ("consume",    "negative, settles a hold on completion"),
        ("release",    "positive, unused portion of a hold"),
        ("refund",     "positive, job failed"),
        ("adjustment", "operator correction; reason required"),
    ]
```

`billing/credits.py` owns the arithmetic — `estimate`, `hold`, `consume`, `release`, `refund` — as pure functions, and is one of the directories gated at 100%. Balance is `SUM(amount)` over the organisation, maintained as a `CreditBalance` summary row written in the same transaction as the entry, with `SELECT … FOR UPDATE` on that row serialising concurrent holds. **The ledger is the truth; the summary is an index**, and a management command rebuilds one from the other.

Two consequences worth having by default:

- Refunding a customer is an `adjustment` row with a reason and an actor, visible in Django admin and in the audit log. The alternative — an `UPDATE` against a balance column — is untraceable by construction.
- A per-organisation daily spend cap is a query over the ledger rather than a new mechanism. Job creation returns 402 with the cap in `details`.

**Credits ship behind a flag, off by default,** on the same terms as custom roles. The models and the service exist from day one so enabling them is a settings change rather than a migration, but seat-priced projects never see a credit meter.

### Billing flow

Stripe-hosted Checkout and Customer Portal. Minimal PCI surface, no card data touches the app.

- `POST /orgs/{slug}/billing/checkout/` → creates a Checkout Session, returns the URL. `automatic_tax` enabled, AUD default, 14-day trial without card.
- `POST /orgs/{slug}/billing/portal/` → returns a Customer Portal URL for plan changes, payment method updates, invoices and cancellation.
- `POST /api/v1/stripe/webhook/` → signature verified, `StripeEvent` recorded, then dispatched.

Handled events: `checkout.session.completed`, `customer.subscription.created|updated|deleted`, `invoice.paid`, `invoice.payment_failed`.

**Seat sync ships behind a flag.** When `BILLING_SEAT_PRICING` is on, seat count syncs to Stripe with proration whenever a membership is created or removed — dispatched from `organizations/services.py` via `transaction.on_commit()`, never inline.

It is a flag rather than a default because a real class of projects is single-tenant-per-user: the organisation exists for future-proofing and for the permission model, but it will never have a second member. On those projects seat sync is code that runs on every membership write, does nothing useful, and can still fail — a Stripe outage breaking organisation creation for a product that does not sell seats. Off by default; on for anything with an invite flow that matters.

Plans and prices are seeded from Stripe by a management command and refreshed nightly by beat. Stripe is the source of truth for pricing; the local rows are a cache.

### Type synchronisation

```
Django (drf-spectacular + allauth spec)
        ↓ openapi.json
    orval
        ↓
packages/api-client/  →  typed fetch functions + TanStack Query hooks + Zod schemas
```

Generated on every `pnpm dev` start and in CI. CI fails if the committed client differs from what regeneration produces — a stale client is a build error, not a runtime surprise. `packages/api-client` is never hand-edited.

### Integration points

| Concern | Service | Notes |
|---|---|---|
| Billing | Stripe | Checkout + Portal + Tax. AUD/GST configured. |
| Email | Resend | Templates authored in react-email, rendered to HTML at build, sent from Django |
| Files | Cloudflare R2 | Presigned direct upload from browser; Django issues the signature and records `FileUpload` |
| Errors | Sentry | Both runtimes, releases tied to git SHA, source maps uploaded |
| Product analytics | PostHog | Client-side, with a server-side capture helper for billing events |
| Social auth | Google | Others are a settings addition, not a code change |
| Third-party OAuth | — | `Connection` model; see below. Distinct from social auth |

### Third-party OAuth connections

Sign in with Google and connect your Google account are different operations, and the template needs to say so, because allauth's `SocialAccount` looks close enough to be reached for and is wrong in every particular.

| | Social auth (allauth) | Connection |
|---|---|---|
| Belongs to | A user | An organisation |
| Purpose | Establishing identity | Acting on an external system |
| Scopes | Minimal, granted at signup | Broad, often restricted, granted later |
| Token lifetime | Discarded after login | Long-lived refresh token, stored encrypted |
| Failure mode | Log in another way | Feature stops working until re-auth |
| Consent moment | Signup | The moment the feature is first used |

The consent moment is the part that bites. Requesting a broad or restricted scope at signup pushes every new user through a scary consent screen for a capability most of them have not asked for, and — for providers whose sensitive scopes require a published, verified, independently-assessed OAuth app — drags the entire signup flow behind that verification. Incremental authorisation exists precisely to avoid this: minimal scope at signup, additional scope at the point of use, separate client where the provider allows it.

So the template ships a `Connection` model rather than overloading `SocialAccount`:

- Organisation-scoped, not user-scoped, with `connected_by` recorded for audit. The person who connects the account is not necessarily the only person who uses it, and their departure should not silently break the integration.
- Tokens encrypted at rest via a single `keel/core/crypto.py` seam backed by an environment key, upgradeable to KMS. Django admin excludes the token fields entirely — there is no view in which they are legitimately readable.
- Decryption happens in the API process or a worker, never in a serializer and never in a template context.
- A `status` field with `reauth_required` as a first-class state, surfaced as a banner. Silent failure on an expired refresh token is the default outcome otherwise, and it is discovered by the customer.
- Scope constraints are expressible as database check constraints where a scope must never be present. Where the product's guarantee is "we cannot do X", the token that would permit X should not be storable.

`init` does not create any connection; the pattern is a documented recipe plus the model, and the first provider is a per-project addition.

---

## 5. Design System

### A note on what a template's design system is for

The frontend-design discipline says: give the product a visual identity that could not be mistaken for anyone else's. That is correct for a product and wrong for a template. A boilerplate with a strong identity is one that every project has to fight. What Keel ships instead is a **token contract** — a small, complete set of variables that a per-project brand pass replaces in one file — plus one shipped default that is deliberately quiet.

`docs/brand-pass.md` makes this an explicit first step of every new project: run the frontend-design process against the real brief, produce a palette and type pairing for *that* product, and replace `packages/ui/theme.css`. Nothing else should need to change.

### Token contract

Single file: `packages/ui/theme.css`. shadcn's CSS-variable convention, OKLCH throughout, light and dark.

**Tokens are declared on a nestable selector, not only on `:root`.** Light and dark are one axis; product surface is a second one, and projects hit it more often than expected — a workspace that reads dark while its settings read light, a public embed that must stay light inside a dark app, a report view themed for print. If the tokens only exist at `:root` and `.dark`, that requirement arrives as a rewrite of the token layer rather than an added block.

```css
:root, [data-theme] { /* every token declared here */ }
.dark, [data-theme][data-mode="dark"] { /* dark overrides */ }
[data-surface="marketing"] { /* optional per-surface overrides */ }
```

The cost is one attribute selector. Components read `var(--x)` and never know which ancestor supplied it, so nothing else changes. Most projects will use `:root` alone and never think about it.

```css
:root {
  /* Surface */
  --background, --foreground
  --card, --card-foreground
  --popover, --popover-foreground
  --muted, --muted-foreground

  /* Intent */
  --primary, --primary-foreground
  --secondary, --secondary-foreground
  --accent, --accent-foreground
  --destructive, --destructive-foreground
  --success, --success-foreground
  --warning, --warning-foreground

  /* Structure */
  --border, --input, --ring
  --radius: 0.5rem
}
```

Everything else derives. A brand pass touches these values and nothing else.

### Shipped default

Deliberately restrained, because it is meant to be replaced.

- **Display / UI:** Instrument Sans — geometric, slightly narrow, holds up at small sizes in dense tables
- **Marketing display:** Instrument Serif — used only on the marketing route group, at large sizes, sparingly
- **Mono:** JetBrains Mono — code blocks, IDs, API keys

Type scale: 12 / 14 / 16 / 18 / 20 / 24 / 30 / 36 / 48px. Spacing on a 4px base. Radius 8px default, 6px on inputs, 12px on cards.

Palette: a cool neutral grey ramp with a single desaturated indigo primary. Not warm cream, not near-black with an acid accent — those read as defaults rather than choices, and on a template they'd read as *the template's* choice imposed on every project.

### Component inventory

**From shadcn, installed at init:** button, input, textarea, select, checkbox, radio-group, switch, label, form, card, dialog, sheet, dropdown-menu, popover, tooltip, tabs, table, badge, avatar, separator, skeleton, alert, command, sonner (toast), calendar, date-picker, pagination.

**Built on top, in `packages/ui`:**

| Component | Purpose |
|---|---|
| `<AppShell>` | Top bar, content container, page header slot |
| `<OrgSwitcher>` | Organisation dropdown with create-new action |
| `<CommandPalette>` | ⌘K — navigation, resource search, actions |
| `<DataTable>` | TanStack Table wrapper: sorting, filters, column visibility, cursor pagination, row selection, bulk actions |
| `<ResourceForm>` | react-hook-form + generated Zod schema, field errors mapped from API 400s |
| `<Can>` | Renders children only when the user holds a permission code. **Presentation only** — never the enforcement point |
| `<EntitlementGate>` | Renders an upgrade prompt instead of the feature when the plan lacks it |
| `<EmptyState>` | Illustration slot, one-line explanation, primary action |
| `<PageHeader>` | Title, breadcrumb, description, action slot |
| `<ImpersonationBanner>` | Persistent, unmissable, with an exit action |
| `<JobTray>` | Live job status over SSE, survives navigation and reload, polls on stream loss |
| `<CreditMeter>` | Balance, pre-flight estimate on the confirm dialog, 402 handling. Rendered only when credits are enabled |
| `<ConnectionCard>` | Third-party account state, connect and disconnect, `reauth_required` prompt |
| `<FileUpload>` | Presigned direct-to-R2 upload with progress, retry, and `FileUpload` row reconciliation |

### Layout — top bar navigation

Per the operator's preference, no sidebar.

```
┌──────────────────────────────────────────────────────────────────────┐
│ [Logo] [Acme Pty Ltd ▾] │ Dashboard  Widgets  Settings │ [⌘K] [◐] [◯]│
└──────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────┐
│  Widgets                                            [ + New widget ] │
│  Manage the widgets in this organisation.                            │
│  ──────────────────────────────────────────────────────────────────  │
│  [Search…]  [Status ▾]  [Columns ▾]                                  │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ ☐  Name              Status      Created        …              │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                              ← Prev   Next →         │
└──────────────────────────────────────────────────────────────────────┘
```

Sticky top bar, 56px. Organisation switcher immediately after the logo so tenant context is always visible — the single most common source of "wrong data" confusion in multi-tenant apps. Content in a max-width container. On mobile the nav links collapse into a sheet; the organisation switcher stays in the bar.

Settings uses a secondary horizontal tab row rather than a nested sidebar: General · Members · Roles · Billing · Audit.

### Routes

```
(marketing)                      # acme.com — indexed, static
  /                              # landing
  /pricing                       # plan comparison, monthly/annual toggle
  /blog                          # MDX index
  /blog/[slug]                   # MDX post
  /legal/terms, /legal/privacy

(auth)                           # no chrome, centred card
  /login  /signup
  /verify-email  /verify-email/[key]
  /reset-password  /reset-password/[key]
  /mfa                           # TOTP challenge
  /invite/[token]                # accept invitation
  /onboarding                    # create first organisation

(app)                            # app.acme.com — AppShell, authenticated
  /                              # → redirect to last-used org
  /[org]                         # dashboard
  /[org]/widgets                 # DEMO — the pattern to copy
  /[org]/widgets/[id]
  /[org]/settings/general
  /[org]/settings/members
  /[org]/settings/roles
  /[org]/settings/billing
  /[org]/settings/audit
  /account/profile
  /account/security              # password, MFA devices
  /account/sessions              # active sessions, revoke
```

MDX via `content-collections` for type-safe frontmatter. Posts are files in the repo, not a CMS — a CMS is a per-project decision.

**`init` can remove the whole `(marketing)` group.** SEO coupling is answer F, and it is genuinely per-project: an internal tool, a product whose marketing site lives on a separate domain, or anything sold through sales rather than search does not want it. Carrying it anyway means three dependencies, a sitemap and robots pipeline, an OG image route and a Lighthouse gate on pages nobody visits. `init` asks, and on "no" deletes the route group, `content-collections`, the MDX content directory, the sitemap and robots routes, and the marketing rows in the Playwright suite.

### Accessibility floor

WCAG 2.1 AA, verified by `axe-core` in the Playwright suite on every route. Focus visible everywhere. Command palette reachable by keyboard. All colour pairs in the shipped theme meet 4.5:1, and `docs/brand-pass.md` requires the same check on any replacement palette.

---

## 6. User Flows

### Signup → first organisation → subscription

```
/signup
  ├─ email + password  ──▶ POST /_allauth/browser/v1/auth/signup
  │                          ├─ 401 + pending email verification flow
  │                          └─ verification email sent (Celery)
  │                                  │
  │                                  ▼
  │                        /verify-email/[key] ──▶ session established
  │
  └─ Google ──▶ /_allauth/browser/v1/auth/provider/redirect
                  └─ Google consent ──▶ callback ──▶ session established
                                                         │
                                                         ▼
                                                  /onboarding
                                    ┌────────────────────┴───────────────┐
                                    │  no invitation pending             │
                                    │  → create organisation             │
                                    │    POST /orgs/                     │
                                    │    (atomic: Org + Owner Membership │
                                    │     + preset Roles + Stripe        │
                                    │     Customer via on_commit)        │
                                    └────────────────────┬───────────────┘
                                                         ▼
                                                  /app/[org]
                                          14-day trial active, no card
                                                         │
                              trial banner ──▶ /app/[org]/settings/billing
                                                         │
                                    POST /billing/checkout/ ──▶ Stripe Checkout
                                                         │
                                        checkout.session.completed webhook
                                                         │
                                    StripeEvent recorded → Subscription upserted
                                                         │
                                              /app/[org] — entitlements live
```

### Invitation

```
Owner: /app/[org]/settings/members → Invite
  POST /orgs/{slug}/members/invitations/ { email, role_id }
    ├─ require Perm.MEMBERS_INVITE
    ├─ check seat entitlement — 402 with upgrade context if exceeded
    ├─ atomic: create Invitation (7-day expiry, signed token)
    └─ on_commit: dispatch invitation email

Recipient clicks link → /invite/[token]
  ├─ not signed in  → signup, prefilled + locked email, then re-resolve
  ├─ signed in, email matches → accept
  │     POST /invitations/{token}/accept/
  │       atomic: Membership created, Invitation.accepted_at set
  │       on_commit: sync Stripe seat quantity (prorated)
  │     → /app/[org]
  ├─ signed in, email differs → "This invitation is for other@acme.com"
  ├─ expired  → "This invitation expired. Ask an admin to resend."
  └─ revoked  → same treatment, no information disclosure
```

### Permission denial

Three distinct failures, three distinct treatments. Conflating them is the common bug.

```
Not authenticated          → 401 → redirect to /login?next=…
Authenticated, no permission → 403 → the action was never rendered
                                     (<Can> hid it); if reached directly,
                                     an inline "You don't have access to
                                     this" panel, not a redirect
Plan lacks the feature     → 402 → <EntitlementGate> renders an upgrade
                                     prompt naming the required plan
Wrong organisation         → 404 → never 403. Existence is not disclosed
                                     across tenant boundaries.
```

### Stripe webhook

```
POST /api/v1/stripe/webhook/
  ├─ verify signature ──────────── fail → 400, log, no retry
  ├─ StripeEvent.objects.get_or_create(id=event.id)
  │     └─ already processed? → 200 immediately (idempotent no-op)
  ├─ enqueue process_stripe_event.enqueue(event_id)
  └─ 200 within 200ms   ← Stripe requires fast ack; work happens async

worker:
  process_stripe_event(event_id)
    ├─ atomic: dispatch to handler, upsert Subscription
    ├─ on failure: retry w/ backoff ×5 → StripeEvent.error + Sentry
    └─ on success: StripeEvent.processed_at
```

### Impersonation

```
Staff: Django admin → user → "Impersonate"
  ├─ require is_staff
  ├─ AuditLog: impersonation.start, impersonator + actor recorded
  ├─ session flagged; every subsequent AuditLog row carries impersonator
  ├─ <ImpersonationBanner> renders on every page, cannot be dismissed
  └─ exit → AuditLog: impersonation.end → staff session restored

Impersonated sessions cannot: change password, manage MFA, start or
cancel a subscription, or delete the organisation. Enforced in
services, not in the UI.
```

---

## 7. API Specification

REST, versioned at `/api/v1/`. OpenAPI generated by drf-spectacular; auth endpoints served by allauth's own spec and merged at client-generation time.

### Conventions

- Cursor pagination on all collections: `?cursor=…&limit=…` → `{ results, next, previous }`
- Filtering via `django-filter`, declared per viewset
- `PATCH` for partial updates; `PUT` is not exposed
- All timestamps ISO 8601 UTC
- All IDs UUIDv7

### Error envelope

```json
{
  "error": {
    "code": "SEAT_LIMIT_EXCEEDED",
    "message": "This plan includes 10 seats. Upgrade to add more.",
    "details": [{ "field": "email", "message": "Already a member." }]
  }
}
```

| Status | Meaning |
|---|---|
| 400 | Shape validation failed at the serializer |
| 401 | No session, or session expired |
| 402 | Plan lacks the feature or the limit is reached |
| 403 | Authenticated, member of the org, denied. `code` carries the `Decision.reason`; `details` carries `Decision.details` |
| 404 | Not found — or exists in another organisation |
| 409 | Domain invariant violated |
| 422 | Semantically invalid but well-formed |
| 429 | Rate limited; `Retry-After` set |

### Endpoints

```
# Identity — served by allauth headless
POST   /_allauth/browser/v1/auth/signup
POST   /_allauth/browser/v1/auth/login
DELETE /_allauth/browser/v1/auth/session
POST   /_allauth/browser/v1/auth/password/request
POST   /_allauth/browser/v1/auth/password/reset
POST   /_allauth/browser/v1/auth/email/verify
GET    /_allauth/browser/v1/auth/provider/redirect
POST   /_allauth/browser/v1/account/authenticators/totp
GET    /_allauth/browser/v1/auth/sessions
DELETE /_allauth/browser/v1/auth/sessions

# Context
GET    /api/v1/me/                       # user + orgs + role + permissions + entitlements
PATCH  /api/v1/me/

# Organisations
GET    /api/v1/orgs/
POST   /api/v1/orgs/
GET    /api/v1/orgs/{slug}/
PATCH  /api/v1/orgs/{slug}/              # org.update
DELETE /api/v1/orgs/{slug}/              # org.delete
POST   /api/v1/orgs/{slug}/transfer/     # org.transfer

# Members, invitations, roles
GET    /api/v1/orgs/{slug}/members/                    # members.view
PATCH  /api/v1/orgs/{slug}/members/{id}/               # members.change_role
DELETE /api/v1/orgs/{slug}/members/{id}/               # members.remove
GET    /api/v1/orgs/{slug}/invitations/                # members.view
POST   /api/v1/orgs/{slug}/invitations/                # members.invite
DELETE /api/v1/orgs/{slug}/invitations/{id}/           # members.invite
POST   /api/v1/invitations/{token}/accept/             # authenticated only
GET    /api/v1/orgs/{slug}/roles/                      # members.view
POST   /api/v1/orgs/{slug}/roles/                      # roles.manage
PATCH  /api/v1/orgs/{slug}/roles/{id}/                 # roles.manage
GET    /api/v1/permissions/                            # the registry, for role editor

# Billing
GET    /api/v1/plans/                                  # public — pricing page
GET    /api/v1/orgs/{slug}/billing/subscription/       # billing.view
POST   /api/v1/orgs/{slug}/billing/checkout/           # billing.manage
POST   /api/v1/orgs/{slug}/billing/portal/             # billing.manage
POST   /api/v1/stripe/webhook/                         # signature auth

# Credits — present only when BILLING_CREDITS is enabled
GET    /api/v1/orgs/{slug}/credits/                    # billing.view — balance + cap
GET    /api/v1/orgs/{slug}/credits/ledger/             # billing.view — paginated
POST   /api/v1/orgs/{slug}/credits/topup/              # billing.manage

# Jobs — Phase 5.5
POST   /api/v1/orgs/{slug}/jobs/                       # 202 {job_id}; Idempotency-Key honoured
GET    /api/v1/orgs/{slug}/jobs/                       # list, filterable by status
GET    /api/v1/orgs/{slug}/jobs/{id}/                  # polling fallback
POST   /api/v1/orgs/{slug}/jobs/{id}/cancel/
GET    /api/v1/orgs/{slug}/jobs/stream/                # SSE, step transitions

# Audit, files
GET    /api/v1/orgs/{slug}/audit/                      # audit.view
POST   /api/v1/orgs/{slug}/files/presign/

# Demo resource — the shape /new-resource generates
GET    /api/v1/orgs/{slug}/widgets/                    # widgets.view
POST   /api/v1/orgs/{slug}/widgets/                    # widgets.create
GET    /api/v1/orgs/{slug}/widgets/{id}/               # widgets.view
PATCH  /api/v1/orgs/{slug}/widgets/{id}/               # widgets.update
DELETE /api/v1/orgs/{slug}/widgets/{id}/               # widgets.delete
```

---

## 8. Development Phases

Eleven phases. Each invariant that requires work appears here as acceptance criteria, not as prose in a section that never becomes a task.

Phase 5.5 is numbered as a half-phase deliberately: it is an addition rather than a correction, and the numbering keeps the v1.0 phase references in `CLAUDE.md`, the slash commands and the deployment docs valid. See §2 on sequencing — Phases 0–4 are built before the first project starts; 5 onward are specified now and built as the first project forces their shape.

---

### Phase 0 — Repository and toolchain · Small

**Deliverables:** pnpm workspace + Turborepo. `apps/api` (Django 6, `uv`), `apps/web` (Next.js 15, App Router, TS strict). `packages/{ui,api-client,eslint-config,tsconfig}`. `infra/compose.dev.yml` with Postgres 17, Redis 7, Mailpit. GitHub Actions skeleton. `.env.example`. Ruff, mypy, ESLint, Prettier, pre-commit. `import-linter` with the `keel/domain/` contract, inert while the directory is absent. `[tool.keel.coverage]` thresholds in `pyproject.toml` and `scripts/check_coverage.py` that enforces them against `coverage.json` (§4, invariant 7).

**Version floor, pinned here so projects inherit it rather than negotiate it:** Python 3.12+, Django 6.0, Postgres 17, Redis 7, Node 22. A project that needs an older Django is a fork, not a configuration.

**One thing to verify at this phase rather than at the phase that needs it:** whether the target Postgres offers the extensions a project is likely to want — `pgvector` above all, since the anticipated Tier 2 extension is embeddings. It is available on Railway, Neon and RDS, but availability is a property of the host and the image tag, and finding out during Phase 5.5 of a real project is a migration away from a managed service under time pressure. Confirm it at Phase 0 and record the answer in `docs/deploy-railway.md`.

**Dependencies:** none

**Acceptance**
- [ ] `docker compose -f infra/compose.dev.yml up` starts Postgres, Redis, Mailpit and nothing else
- [ ] `pnpm dev` runs Django and Next natively, both hot-reloading
- [ ] `pnpm lint`, `pnpm typecheck`, `pnpm test` pass across all workspaces
- [ ] CI runs all three on push, with coverage evaluated per directory rather than globally
- [ ] `scripts/check_coverage.py` fails on a path below its threshold and on a glob that matches nothing, naming the path and both figures
- [ ] Adding a file to `keel/domain/` that imports the ORM fails CI; the contract is silent while the directory is absent
- [ ] Mailpit catches a test email at `localhost:8025`
- [ ] `CREATE EXTENSION vector` succeeds on the dev image and the answer for the target host is recorded

---

### Phase 1 — Django foundation · Medium

**Deliverables:** split settings. Custom `User` (UUIDv7 pk via `keel/core/ids.py`, email as `USERNAME_FIELD`). `keel/core`: `TimestampedModel`, `OrgScopedModel`, `OrgScopedQuerySet`, `OrgScopedViewSet`, `keel/core/authz.py` (`Decision`, the `Guard` protocol, the registry and `HasOrgPermission`), `keel/core/audit.py` (`@audited`, `@not_audited`), domain exception hierarchy and DRF exception handler producing the error envelope, cursor pagination, `keel/core/tasks.py` shim. drf-spectacular. CORS with credentials. Structured JSON logging.

**Plus the baseline migration** (§4, data model): every table in the data model created once, with final columns and constraints, before any phase writes a service against it.

**Dependencies:** Phase 0

**Acceptance**
- [ ] `/api/v1/schema/` serves a valid OpenAPI 3.1 document
- [ ] Every documented status code maps to the error envelope, verified by test
- [ ] `makemigrations --check --dry-run` gates CI
- [ ] `OrgScopedViewSet` raises at import time if a subclass declares no `required_permissions`
- [ ] Any viewset declaring neither `organization_scoped = True` nor a `GLOBAL_JUSTIFICATION` string fails at import
- [ ] A viewset with `organization_scoped = True` and no `test_factory` fails at import
- [ ] `keel/core` imports nothing from `keel/organizations` — enforced by an import-linter contract, not by convention
- [ ] The baseline migration applies to an empty database and `makemigrations --check --dry-run` is clean immediately afterwards

---

### Phase 2 — Authentication · Large

**Deliverables:** django-allauth headless, `HEADLESS_ONLY`. Email/password, verification, reset, Google OAuth. MFA (TOTP) scaffolded and disabled by a settings flag. `allauth.usersessions`. `HEADLESS_FRONTEND_URLS` pointed at Next routes. Cookie configuration for the shared registrable domain. CSRF handling in the web client. Next.js middleware route guards. Auth pages: login, signup, verify-email, reset-password, MFA challenge. Account pages: profile, security, sessions.

**Dependencies:** Phase 1

**Acceptance**
- [ ] Signup → verification email in Mailpit → click → authenticated session
- [ ] Google OAuth completes and creates a user
- [ ] Password reset round-trips end to end
- [ ] Session cookie is HttpOnly, Secure, SameSite=Lax, scoped to the parent domain
- [ ] Unauthenticated access to `/app/*` redirects to `/login?next=…`
- [ ] TOTP enrolment and challenge work when the flag is enabled
- [ ] A user can list and revoke their own sessions
- [ ] Playwright covers signup, login, logout, reset

---

### Phase 3 — Organisations, members, permissions · Large

**The most consequential phase.** Everything downstream assumes it is correct.

**Deliverables:** `Organization`, `Membership`, `Role`, `Invitation` models and services. Permission registry. `Decision`. `has_perm()`. `HasOrgPermission`. Preset role seeding on org creation. Invitation lifecycle with signed tokens and expiry. Organisation switcher. Settings pages: General, Members, Roles. `<Can>` component. Custom-roles feature flag. **The two CI meta-tests.**

**Dependencies:** Phase 2

**Acceptance**
- [ ] Creating an organisation is atomic: org, Owner membership, three preset roles, all or nothing
- [ ] Every registered guard has both an allow and a deny test, and the deny test asserts the `reason`
- [ ] **Meta-test fails CI if any registered guard lacks both tests**
- [ ] A denial reaches the client as a 403 whose `code` is the `Decision.reason`, verified end to end for at least one role denial and one state denial
- [ ] A guard that inspects a subject (not only the role) exists, is registered like any other, and is declared on a viewset the same way
- [ ] **Meta-test walks every viewset, asserts cross-org access returns 404 for the scoped ones, and prints every `GLOBAL_JUSTIFICATION` in CI output**
- [ ] `grep` for permission checks outside `permissions.py` returns nothing; a CI lint rule enforces it
- [ ] Invitation accepted by the wrong email is rejected without disclosing the invitee
- [ ] Expired and revoked invitations are indistinguishable to the recipient
- [ ] The last Owner cannot be removed or demoted
- [ ] `<Can>` hides actions; removing it client-side still yields 403 from the API

---

### Phase 4 — Billing · Large

**Deliverables:** `Plan`, `Price`, `Subscription`, `StripeEvent`. `CreditLedgerEntry`, `CreditBalance` and `billing/credits.py`, behind `BILLING_CREDITS`, off by default. `sync_stripe_plans` command. Checkout and Portal session endpoints with `automatic_tax`, AUD, 14-day cardless trial. Webhook endpoint with signature verification and idempotency. Entitlement resolution, `@requires_entitlement`, `check_limit`. Seat sync on membership change with proration, behind `BILLING_SEAT_PRICING`, off by default. Pricing page. Billing settings page. `<EntitlementGate>`. Trial and dunning banners.

**Dependencies:** Phase 3

**Acceptance**
- [ ] Checkout completes and the subscription appears without manual intervention
- [ ] **Every handled webhook event replayed twice produces identical state**
- [ ] An unsigned or wrongly-signed webhook returns 400 and changes nothing
- [ ] Webhook endpoint acknowledges in under 200ms; processing is async
- [ ] Adding a member beyond the seat entitlement returns 402 with upgrade context
- [ ] With `BILLING_SEAT_PRICING` on, removing a member decrements the Stripe quantity with proration; with it off, no Stripe call is made and membership writes succeed while Stripe is unreachable
- [ ] **Three concurrent holds against a balance sufficient for two produce exactly two holds and one 402** — the double-spend test, run against a real database
- [ ] A failed job's hold is fully refunded; a job finishing under estimate releases the remainder; balance equals `SUM(amount)` after every case
- [ ] Rebuilding `CreditBalance` from the ledger reproduces the same number
- [ ] An operator adjustment in Django admin requires a reason and writes an audit row
- [ ] Plan downgrade below current usage is blocked with a clear message
- [ ] `payment_failed` puts the org into a dunning state; the banner appears; access is not immediately revoked
- [ ] Stripe test-clock scenarios cover trial end, renewal and cancellation

---

### Phase 5 — Async, email, files · Medium

**Deliverables:** Celery worker and beat in the same image. Task shim finalised. Retry policy, dead-letter, `FailedTask`. Beat schedule (six jobs, §4). Resend integration. react-email templates: verification, reset, invitation, trial ending, payment failed, seat added. R2 presigned uploads. `<FileUpload>` component.

**Dependencies:** Phases 2–4

**Acceptance**
- [ ] All six scheduled jobs run and are idempotent when run twice
- [ ] A task raising an exception retries five times with backoff, then dead-letters with a Sentry event
- [ ] Every task body is a single call into a service — verified by lint
- [ ] Tasks take IDs, never model instances — verified by lint
- [ ] All six emails render and send, and are caught by Mailpit in dev
- [ ] Presigned upload completes from the browser; `FileUpload` reaches `complete`
- [ ] Uploads are scoped to the organisation and cannot be read across tenants

---

### Phase 5.5 — Long-running jobs and live status · Medium

**Numbered as a half-phase because it is the one addition in v1.1 that is not a correction to something already specified.** It earns its place on the argument the stack section already makes: the anticipated per-project extension is Tier 2 data and AI work, and that work is minutes-long, not milliseconds-long. A template whose async story stops at "send this email later" hands every such project the same three weeks of infrastructure to rebuild.

**Deliverables:** `Job` and `JobStep` behaviour — the tables themselves already exist from the baseline migration, and this phase adds no schema (`FailedTask` likewise exists, from the baseline, and is wired up in Phase 5). A job registry declaring each type's steps, queue and credit estimate. A base task class handling step transitions, per-step commits, resumption from the last completed step, and terminal status resolution including `partial`. `Idempotency-Key` middleware on job-creating POSTs, stored 24 hours. Per-organisation concurrency limits via a Redis semaphore. Redis pub/sub publication of step transitions. An SSE endpoint on the ASGI app. `useJobStream` hook with automatic fallback to polling. `<JobTray>` — persistent, survives navigation and reload. Dead-letter re-drive action in Django admin for the `FailedTask` rows Phase 5 introduced. One demo job type with three steps, deleted by `init` alongside the demo resource.

**Two deployment footguns this phase exists to prove out, rather than discovering them in a project:**

1. **SSE holds a connection for its entire life.** Under a sync worker model, every connected browser occupies a worker and the pool exhausts at a user count far below what load testing on request/response traffic suggests. The API must serve the stream endpoint from an async worker, and the acceptance criteria below put a number on it.
2. **Reverse proxies buffer by default.** A proxy that buffers a text/event-stream will hold the response until the connection closes, and the symptom is not an error — it is a job tray that shows nothing for four minutes and then everything at once, which reads as "the feature is broken" and is very hard to attribute. Correct headers, correct proxy configuration, and a test that asserts first-byte latency rather than only final content.

A third, smaller: HTTP/1.1 caps concurrent connections per host at six per browser. The stream takes one. On a shared API subdomain this leaves five for everything else, which is survivable but worth knowing before someone opens the app in four tabs and reports that it hangs.

**Dependencies:** Phases 3–5

**Acceptance**
- [ ] A job created via POST returns 202 in under 300ms with the work not yet started
- [ ] The same request replayed with the same `Idempotency-Key` returns the original job and creates no second row and no second credit hold
- [ ] Steps stream to the browser as they transition; **first event reaches the client in under one second**, which is the assertion that catches proxy buffering
- [ ] Killing the worker mid-job and restarting resumes at the last completed step rather than from the beginning
- [ ] A job that partially succeeds reaches `partial`, surfaces its results, and releases the unused hold
- [ ] Dropping the SSE connection falls back to polling and the tray stays correct throughout
- [ ] The tray survives a full page reload with jobs still running
- [ ] One organisation saturating its concurrency limit does not delay another organisation's job
- [ ] 50 concurrent SSE connections leave the API serving normal requests at unchanged p95
- [ ] An exhausted task lands in `FailedTask` and is re-drivable from admin

---

### Phase 6 — App shell and the demo resource · Medium

**Deliverables:** `<AppShell>` with the top bar. `<OrgSwitcher>`. `<CommandPalette>`. `<DataTable>`. `<ResourceForm>`. `<PageHeader>`, `<EmptyState>`. Dark mode. Dashboard. **The `Widget` resource, built end to end as the canonical pattern**: model → service → selector → permissions → serializer → viewset → tests → client regeneration → list page → detail page.

**Dependencies:** Phases 3–5

**Acceptance**
- [ ] Organisation switching updates the route and refetches all data
- [ ] Command palette navigates and searches resources by keyboard alone
- [ ] Data table sorts, filters, paginates by cursor, and bulk-deletes with permission checks
- [ ] Form errors from a 400 map to the correct field
- [ ] Widget CRUD works end to end with permission enforcement at every action
- [ ] Dark mode has no contrast failures
- [ ] Every empty state offers a primary action

---

### Phase 7 — Marketing site and blog · Small

**Deliverables:** `(marketing)` route group. Landing page. Pricing page reading live from `/api/v1/plans/`. MDX blog via `content-collections`. Legal pages. `sitemap.xml`, `robots.txt`, Open Graph images, JSON-LD.

**Dependencies:** Phase 4

**Acceptance**
- [ ] Marketing routes are statically rendered and score ≥ 95 on Lighthouse SEO
- [ ] Pricing reflects Stripe without a redeploy
- [ ] A new MDX file appears in the index with typed frontmatter validation
- [ ] Sitemap includes marketing and blog routes and excludes the app — which is a separate host as of v1.3, so exclusion is by host, not by path prefix

---

### Phase 8 — Observability, audit, hardening · Medium

**Deliverables:** Sentry on both runtimes with release tracking and source maps. PostHog. `AuditLog` with a service-layer `record()` helper and the `@audited` decorator described below. Audit settings page. Staff impersonation with banner and restrictions. API rate limiting. Security headers. `axe-core` in Playwright. k6 smoke load test.

**The service registry, specified.** v1.1 asserted a meta-test "over the service registry" without ever saying what that registry was. It is `keel/core/audit.py`: an `@audited(action)` decorator applied to mutating service functions, which records the action, actor, impersonator, target and metadata on commit, and — as a side effect of being a decorator — populates a module-level registry of every service that has been marked. The meta-test walks every `services.py`, collects the public callables that mutate (identified by the `@audited` or an explicit `@not_audited(reason=...)` marker), and fails on any that carries neither. As with `GLOBAL_JUSTIFICATION`, the escape hatch costs a sentence and appears in CI output; the default costs nothing.

**Dependencies:** Phases 3–6

**Acceptance**
- [ ] A deliberate error appears in Sentry with the correct release and readable stack
- [ ] Every mutating service is decorated `@audited` or `@not_audited(reason=...)`; a meta-test fails on any that is neither, and prints every reason
- [ ] An audited service writes exactly one audit row per call, on commit, carrying actor and impersonator
- [ ] Impersonated sessions are recorded and cannot perform the four restricted actions
- [ ] Rate limits return 429 with `Retry-After`
- [ ] `axe-core` reports zero violations on all routes
- [ ] k6 sustains 100 rps on the widget list with p95 under 300ms

---

### Phase 9 — Template mechanics · Medium

> **Renumbered to Phase 17** in the v1.4 sequence. The content below is unchanged and remains the specification; only its slot moved. Implementation plan: `docs/plans/phase-17.md`.

**The phase that makes it a template rather than an app.**

**Deliverables:** `scripts/init.ts`; GitHub template repository configuration; `CLAUDE.md`; slash commands; deployment docs for Railway and self-host.

**What `init` prompts for:**

| Prompt | Effect |
|---|---|
| Project name | Renames the Python package and every reference |
| App, marketing and API domains | Written into settings; refuses to complete without all three. The app is its own subdomain (v1.3) — `app.acme.com`, `acme.com`, `api.acme.com` — and `init` also writes the `lvh.me` dev equivalents |
| **Tenant noun** | Model name, URL segment, permission-code prefix, route param, component names, UI copy |
| Stripe keys | `.env`, plan sync |
| **Marketing site?** | On "no", deletes the `(marketing)` group, `content-collections`, the MDX directory, sitemap and robots routes, and the marketing Playwright rows |
| **Billing shape** | Seats, credits, both or neither — sets `BILLING_SEAT_PRICING` and `BILLING_CREDITS` |
| **Demo slice: delete or keep as reference?** | See below |
| Pure domain layer? | Creates `keel/domain/` and activates the import-linter contract |

It also rewrites `.env.example`, resets git history, and writes `docs/brand-pass.md` as a first-task checklist.

**On the demo slice.** v1.0 had `init` delete `widgets` unconditionally, on the reasoning that speculative code should not survive instantiation. That reasoning holds for code that *runs*. It does not hold for the canonical pattern, which is the single most useful thing to point Claude Code at during a build that may last months — "make this look like the reference slice" is a far better instruction than a prose description of the same thing, and the alternative is that someone copies the shape from a half-finished feature written on a bad day.

So `init` offers two answers. **Delete** removes the app, its migrations, routes, tests and client entries. **Keep as reference** moves the whole vertical slice to `docs/reference-slice/` as inert files — no app registration, no migration, no route, not importable, excluded from coverage — and points `CLAUDE.md` at it. Default is keep; delete is one flag away and can be run later.

**`CLAUDE.md` must contain:** the seven invariants verbatim; the per-app file structure with the rule for each file; whether this project uses the pure domain layer; the permission registry pattern and the `Decision` shape; the three resource recipes below and when each applies; the explicit prohibitions (no logic in views, no authorization outside `permissions.py`, no Stripe calls inside transactions, no hand-edits to `packages/api-client`, no schema changes outside migrations, no extending the task shim to cover multi-step work).

**Slash commands in `.claude/commands/`:**

| Command | Does |
|---|---|
| `/new-resource <n>` | Full CRUD vertical slice: model, service, selector, permission codes registered, serializer, viewset, tests including allow/deny, client regeneration, list and detail pages |
| `/new-readonly-resource <n>` | The same slice for entities users read but never write — worker output, derived records, imported data. Registers view codes only, generates no create/update/delete path, and scaffolds the service that *writes* it as an internal function with no HTTP surface |
| `/new-job <n>` | Job type registered with its steps, queue, credit estimate and idempotency key; per-step task bodies delegating to services; enqueue-and-assert-persisted tests; a resumability test; client-side tray entry |
| `/new-permission <code>` | Registers the guard, adds it to the appropriate presets, scaffolds the allow/deny tests |
| `/new-connection <provider>` | `Connection` subtype, OAuth callback, encrypted token storage, `reauth_required` banner wiring, scope constraint |
| `/check-invariants` | Runs the meta-tests, the import-linter contract and the lint rules, and reports which invariant any failure maps to |
| `/sync-client` | Regenerates OpenAPI and the TypeScript client, fails loudly on drift |
| `/new-email <n>` | react-email template, Django dispatch function, preview route |

The reason `/new-readonly-resource` exists as its own command rather than a flag: most non-trivial products have more worker-written tables than user-written ones, and generating `widgets.create`, `widgets.update` and `widgets.delete` codes for a table no user ever writes to fills the permission registry with entries that can never be exercised — which then need allow and deny tests, under the meta-test, forever. The registry stops being readable, which is the property the whole authorization invariant depends on.

**Dependencies:** all previous phases

**Acceptance**
- [ ] `init` produces a running project with a new name and zero references to "keel"
- [ ] Choosing a different tenant noun leaves no occurrence of the old one in models, URLs, permission codes, routes, components or copy
- [ ] Declining the marketing site leaves no orphaned dependency, route, or failing Lighthouse gate
- [ ] `init` removes the demo resource completely on "delete" — no orphaned migrations, routes, tests or client entries — and on "keep" leaves it inert, unimportable, and excluded from coverage
- [ ] `/new-resource Invoice` produces a working, permission-enforced, tested CRUD slice with no manual edits
- [ ] `/new-readonly-resource Report` registers exactly one permission code and exposes no write endpoint
- [ ] `/new-job import_csv` produces a job that streams, resumes, and holds credits when credits are enabled
- [ ] `/check-invariants` catches a deliberately misplaced permission check and a deliberate ORM import inside `keel/domain/`
- [ ] Both deployment guides work end to end from a clean account
- [ ] A fresh instantiation reaches a deployed authenticated app in under 4 hours

---

## 9. Extension Points

Named seams for the things explicitly out of scope, so adding them later is a known move rather than a redesign.

| Deferred | Seam already in place |
|---|---|
| Mobile client | allauth `X-Session-Token` / JWT strategy, configured and disabled |
| Bidirectional realtime | Django Channels on the same ASGI app; Redis already present. Server-to-client streaming is no longer deferred — it ships in Phase 5.5 as SSE, which covers job status, notifications and live counters without a second protocol. Channels is for the genuinely bidirectional case: collaborative editing, presence, chat |
| Metered billing | Shipped, behind `BILLING_CREDITS` — the ledger, the balance row and the arithmetic |
| Long-running work | Shipped in Phase 5.5 — `Job`, `JobStep`, resumability, partial success, streaming |
| Third-party integrations | `Connection` model with encrypted tokens, `reauth_required` state, and `/new-connection` |
| SSO / SAML | allauth ships a SAML provider; the org model already supports domain claiming |
| i18n | No hardcoded strings in `packages/ui`; copy in a single module per route group |
| AI / Tier 2 | A Python backend with a worker pool, a job primitive, a credit ledger and an optional pure domain layer. Add a `keel/ai` app; heavy inference goes to a separate service, called from tasks, never from views |
| Embeddings / vector search | `pgvector` availability confirmed at Phase 0 and recorded in the deployment docs |
| Custom domains per org | `Organization.slug` is already the routing key |
| Per-surface theming | Tokens are declared on a nestable selector, not only `:root` |

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| The subdomain cookie constraint is forgotten on a new project and login silently fails in production | `init` refuses to complete without both domains; a startup check fails loudly on a mismatched `SESSION_COOKIE_DOMAIN` |
| Vercel preview deploys break auth | Wildcard preview domain configured at `init`; documented as requiring Vercel Pro |
| `lvh.me` stops resolving, or a developer works offline, and dev auth breaks with no obvious cause | `docs/dev-setup.md` documents a hosts-file fallback (`keel.test`) and the reason the shared-cookie constraint rules out `app.localhost`. The failure is loud — nothing resolves — rather than the silent cookie failure `app.localhost` would produce |
| A phase adds a build artefact the test suite silently depends on | `packages/emails` did exactly this: its rendered HTML is required by every mail-sending flow, is not committed, and CI had no step to produce it. A root `conftest.py` now fails at collection naming the command to run. The general lesson is that a worktree passing does not mean a fresh clone passes |
| Two deploys drift — API and web versions mismatch | Generated client checked into the repo; CI fails on drift; both deploy from the same commit |
| The template accretes features nobody needed | Every addition must trace to a real project requirement; every v1.1 change traces to a named conflict with the first instantiation; the demo slice is the only speculative code and `init` removes or quarantines it |
| Phase 5.5 is the template guessing at a project's job system, and the project needs a different one | It ships as the primitive, not the workflow — rows, transitions, streaming, resumption. Anything about *what* a job does stays in the project. If the first real project rewrites more than the registry, the phase was wrong and should shrink |
| The `Decision` return type is more machinery than most projects need | It is one dataclass and two constructors. A guard that only checks a role reads almost identically to the boolean version. The cost is paid once; the alternative is a project discovering mid-build that its guards do not fit the type |
| Backporting from the first project to the template never happens | Accepted openly in §2. Phases 5–9 exist as written specifications, so a lift is a port rather than a design. If nothing has been backported by the end of the first project, that is the signal to stop maintaining Keel as a template and treat it as that project's history |
| Celery adds ops burden for a solo operator | Worker and beat run in the same image as the API; Railway treats them as extra services on the same deploy; Flower is optional |
| Granular permissions become unmanageable | Custom roles ship behind a flag, off by default. Most projects run three presets and never enable it |
| The three phases Laravel would have given free never feel worth it | Revisit after the third instantiation. If it still doesn't feel earned, that is a real signal about the stack choice, not about the template |

---

## Appendix — Dependency manifest

**Backend:** Django 6.0 · djangorestframework · drf-spectacular · django-allauth[headless-spec,mfa,socialaccount] · django-cors-headers · django-filter · celery · redis · psycopg[binary] · stripe · boto3 · resend · sentry-sdk · django-storages · cryptography · uuid-utils · gunicorn · uvicorn · uv
*On `uuid-utils`:* IDs are UUIDv7 and `uuid.uuid7` is Python 3.14+. The floor is 3.12, so the generator is a dependency rather than the standard library, isolated behind `keel/core/ids.py` so it becomes a one-line deletion when the floor moves.
*Dev:* pytest · pytest-django · pytest-cov · pytest-asyncio · factory-boy · freezegun · ruff · mypy · django-stubs · import-linter
*Per-project, not shipped:* pgvector (availability confirmed at Phase 0)

**Frontend:** next@15 · react@19 · typescript · tailwindcss · shadcn/ui · @tanstack/react-query · @tanstack/react-table · react-hook-form · zod · lucide-react · sonner · next-themes · cmdk · content-collections · @sentry/nextjs · posthog-js · react-email
*Dev:* vitest · @testing-library/react · @playwright/test · @axe-core/playwright · orval · eslint · prettier

**Infra:** Vercel (web) · Railway (api, worker, beat, Postgres 17, Redis 7) · Cloudflare R2 · Stripe · Resend · Sentry · PostHog
*Note:* SSE is served by a dedicated uvicorn service running the same image, declared in `railway.json`, whose proxy must not buffer `text/event-stream` (Phase 5.5).
*Self-host alternative:* Hostinger VPS + Coolify + Caddy, `infra/compose.prod.yml`
