# Phase 1 — Django foundation and the baseline migration

**Owner:** one Sonnet agent, working directly on `master` in the primary checkout.
**Source of truth:** `keel-prd.md` v1.2 — §4 "Django app layout", all seven Architecture Invariants, "Data model", "Credits", "Type synchronisation", §7 "Error envelope", and §8 Phase 1.
**Depends on:** Phase 0, complete and verified.
**Size:** Large. This is the phase every later phase is built on top of, and it is the only phase that writes migrations.

---

## What this phase is

Two things, and they are related:

1. **`keel/core`** — the primitives every app depends on and no app may bypass: identifiers, base models and querysets, the authorization vocabulary, the audit decorators, the exception hierarchy and its HTTP envelope, cursor pagination, the task shim, and the encryption seam.
2. **The baseline migration** — every table in the PRD's data model, created once, with final columns and constraints, before any phase writes a service against it.

The second is the reason this phase is worth doing carefully. PRD v1.2 makes it policy: implementation branches inherit the schema and do not generate migrations. If a table is wrong here, three later worktrees discover it at once and each fixes it differently.

---

## Boundary

**In scope:** `keel/core`, the custom `User`, every model in the PRD data model, one migration per app, DRF and drf-spectacular configuration, CORS with credentials, structured JSON logging, and tests for all of it.

**Out of scope — do not write these:**

| Thing | Owner |
|---|---|
| Any `services.py`, `selectors.py`, `views.py`, `serializers.py` in a domain app | Phases 2–6 |
| The permission **codes** and their guard implementations (`organizations/permissions.py`) | Phase 3 |
| allauth, any auth flow, any login page | Phase 2 |
| Stripe calls, checkout, webhooks, entitlement resolution, credit arithmetic | Phase 4 |
| Celery task bodies, beat schedule, email templates | Phase 5 |
| Job execution, step transitions, SSE | Phase 5.5 |
| Any React component or route | Phases 2–7 |
| `keel-prd.md`, anything under `docs/plans/` | The orchestrator |

You are building the vocabulary and the tables. Other agents put words in it.

**Critical distinction, and the thing most likely to be got wrong:** `keel/core/authz.py` contains the `Decision` dataclass, the `Guard` protocol, the registry object, `HasOrgPermission`, and the base viewsets. It contains **no permission code, no role, and nothing that answers a question about a user.** Phase 3 imports the registry and fills it. If you find yourself writing the string `"org.view"` in `keel/core`, stop.

---

## Tasks

### 1.1 — Two new Django apps

The PRD's data model contains tables the Phase 0 app list has nowhere to put. Create:

- `keel/jobs/` — `Job`, `JobStep`, `FailedTask`
- `keel/connections/` — `Connection`

Register both in `INSTALLED_APPS`. They get models in this phase and behaviour in Phases 5 and 5.5. Do **not** put these in `keel/core` — core holds primitives, not domain tables.

Record this as a deviation in your report: the PRD's §4 app list omits both, and it should be updated.

### 1.2 — `keel/core/ids.py`

UUIDv7 primary keys, per PRD §7 conventions and the v1.2 manifest note. `uuid.uuid7` is Python 3.14+; the floor is 3.12, so this wraps `uuid-utils` behind a single function so it becomes a one-line deletion when the floor moves.

Provide the generator and a `UUIDv7PrimaryKey` field or model mixin. Test that generated ids sort in creation order — that is the property being bought and the reason not to use uuid4.

### 1.3 — `keel/core/models.py`

- `TimestampedModel` — `created_at`, `updated_at`, abstract.
- `OrgScopedQuerySet` — `for_organization(org)`, and whatever the base viewset needs.
- `OrgScopedModel` — abstract, `organization` FK, `objects = OrgScopedQuerySet.as_manager()`, indexed on `organization`.
- A `SoftDeleteModel` mixin only if the data model needs it (`Organization.deleted_at` does). Do not generalise beyond what a table actually uses.

### 1.4 — `keel/core/exceptions.py` and the error envelope

The domain exception hierarchy, and a DRF exception handler producing exactly the envelope in PRD §7:

```json
{ "error": { "code": "...", "message": "...", "details": [...] } }
```

Every status code in the PRD's table must map: 400, 401, 402, 403, 404, 409, 422, 429. Typed domain exceptions for the 402 / 409 / 422 cases. `Retry-After` on 429.

**Test every row of that table**, asserting the response body shape, not only the status. This is a Phase 1 acceptance criterion and it is easy to satisfy shallowly.

### 1.5 — `keel/core/authz.py`

Per PRD v1.2, invariant 2, "Where the type lives, and why it is not in this file":

- `Decision` — frozen dataclass, `allowed` / `reason` / `details`, with `Decision.allow()` and `Decision.deny(reason, details=None)`.
- A `Guard` protocol: callable taking `(user, organization, subject=None)` and returning a `Decision`.
- A registry object: register a code with its guard, look one up, iterate all registered entries. Iteration is what Phase 3's meta-test walks, so it must be a stable, inspectable surface — not a bare dict comprehension buried in a closure.
- `has_perm(user, organization, code, subject=None) -> Decision` — resolves through the registry. Raise a clear error on an unregistered code; a typo must not silently deny.
- `HasOrgPermission` — the DRF permission class. Reads `required_permissions` off the view, calls `has_perm`, and on denial produces a 403 whose envelope `code` is the `Decision.reason` and whose `details` is the `Decision.details`.
- `OrgScopedViewSet` and `GlobalViewSet` base classes, with the **import-time** checks:
  - a subclass declaring no `required_permissions` raises;
  - a subclass declaring neither `organization_scoped = True` nor a `GLOBAL_JUSTIFICATION` string raises;
  - a subclass with `organization_scoped = True` and no `test_factory` raises.
  Use `__init_subclass__`. "At import time" means the failure happens when the module is imported, not when a request arrives.
- `OrgScopedViewSet` resolves the organisation from the URL, checks membership, and filters the queryset **before any view code runs**. Because `keel/core` cannot import `keel.organizations`, resolve the membership through a settings-configured callable or a registry hook that Phase 3 supplies. Design that seam deliberately and document it — it is the one genuinely awkward consequence of the v1.2 split, and getting it wrong means Phase 3 either can't wire it or reaches around it.

`keel/core` must not import `keel.organizations`. The import-linter contract from Phase 0 already asserts this and must stay green.

### 1.6 — `keel/core/audit.py`

Per PRD v1.2, Phase 8, "The service registry, specified":

- `@audited(action)` — decorator for mutating service functions. Records the action, actor, impersonator, target and metadata **on commit**. Registers the decorated function in a module-level registry.
- `@not_audited(reason)` — the escape hatch, also registered, with its reason retrievable.
- The registry is walkable: Phase 8's meta-test needs to enumerate every marked function and its marker.

In this phase the decorators must record correctly and register correctly. There are no services to decorate yet, so test them against fixture functions.

### 1.7 — `keel/core/pagination.py` and `keel/core/tasks.py`

- Cursor pagination, DRF, returning `{ results, next, previous }` per PRD §7. Ordering must be stable — cursor pagination on a non-unique sort key skips and repeats rows, which is the classic silent bug. Test with a page boundary falling inside a run of equal sort values.
- The task shim: roughly twenty lines mirroring `django.tasks` (`@task` / `.enqueue()`) executing on Celery. **Tier 1 only.** PRD invariant 5 is explicit that it must not grow to cover multi-step work — do not add chaining, routing, or step semantics. Include the docstring saying so.

### 1.8 — `keel/core/crypto.py`

The encryption seam for `Connection` tokens (PRD, "Third-party OAuth connections"): encrypt/decrypt backed by an environment key, structured so a KMS backend replaces the body without touching call sites. Add the key to `.env.example`. Test round-trip and test that a wrong key fails loudly rather than returning garbage.

### 1.9 — Custom `User`

`accounts/models.py`: UUIDv7 pk, `email` unique and `USERNAME_FIELD`, `name`, `avatar_url`, `is_staff`, `is_active`, `date_joined`. Custom manager. `AUTH_USER_MODEL` set. No allauth yet — Phase 2 attaches to this.

### 1.10 — The rest of the data model

Every table in PRD §4 "Data model", in its app, with the columns and constraints as written:

| App | Tables |
|---|---|
| `accounts` | `User` (1.9) |
| `organizations` | `Organization`, `Role`, `Membership`, `Invitation` |
| `billing` | `Plan`, `Price`, `Subscription`, `StripeEvent`, `CreditLedgerEntry`, `CreditBalance` |
| `connections` | `Connection` |
| `jobs` | `Job`, `JobStep`, `FailedTask` |
| `audit` | `AuditLog` |
| `files` | `FileUpload` |
| `widgets` | `Widget` |

Points that need deliberate decisions rather than defaults:

- **`StripeEvent.id` is the Stripe event id**, a string primary key, not a UUID. Idempotency depends on it.
- **`CreditBalance` is one-to-one with `Organization` and that FK is the primary key.** `SELECT … FOR UPDATE` on that row is what serialises concurrent holds in Phase 4.
- **`CreditLedgerEntry` is append-only.** No triggers (invariant 7 forbids database logic), so this is enforced by service discipline and tested there. Index it for `SUM(amount)` per organisation.
- **`Connection.access_token` / `refresh_token`** use the `keel/core/crypto.py` seam and are **excluded from Django admin entirely** — there is no view in which they are legitimately readable.
- `unique(organization, user)` on `Membership`; `unique(organization, provider, external_account)` on `Connection`; `unique` on `Invitation.token`, `Price.stripe_price_id`, `Subscription.stripe_subscription_id`, `Plan.code`, `Organization.slug`, `FileUpload.key`.
- `AuditLog.organization` and `AuditLog.actor` are both nullable; `impersonator` is nullable and unread until Phase 8.
- Every org-scoped table is indexed on `organization`, and on `(organization, created_at)` where it will be cursor-paginated.
- `Job` and `JobStep` are **schema only** in this phase (PRD v1.2 change 2). No task base class, no step transitions.

Django admin registration: register models where it is useful for inspection, with `Connection` token fields excluded. Do not build admin actions — impersonation and ledger adjustments are Phases 8 and 4.

### 1.11 — One baseline migration per app, in one commit

Generate them, read them, and commit them together. Then:

- `makemigrations --check --dry-run` must be clean immediately afterwards.
- The migration must apply to an empty database.
- Reverse it and re-apply it. If a migration is not reversible, say so explicitly and why.

### 1.12 — DRF, drf-spectacular, CORS, logging

- Install and configure `drf-spectacular`. `/api/v1/schema/` serves a valid **OpenAPI 3.1** document — validate it with a real validator, not by eyeballing that the endpoint returns 200.
- DRF defaults: the cursor pagination class, the exception handler, session authentication, and `DEFAULT_PERMISSION_CLASSES` set to something that denies by default.
- CORS with credentials, configured for the app/API domain split described in PRD "Auth architecture". Do not use a wildcard origin — credentialed CORS forbids it and the failure is confusing.
- Structured JSON logging, request id on every line.

### 1.13 — Coverage thresholds

Raise the `[tool.keel.coverage]` entries for the paths this phase creates. `keel/core` carries real obligations now: the authz registry, the exception handler and the pagination class are all load-bearing and all cheap to test. Set thresholds you actually meet, and say in the report what you set and why.

---

## Acceptance — every box needs pasted evidence

From PRD §8 Phase 1, including the v1.2 additions:

- [ ] `/api/v1/schema/` serves a valid OpenAPI 3.1 document, validated by a validator
- [ ] Every documented status code maps to the error envelope, verified by test — one test per row of the §7 table, asserting the body
- [ ] `makemigrations --check --dry-run` gates CI and is clean
- [ ] `OrgScopedViewSet` raises **at import time** if a subclass declares no `required_permissions`
- [ ] A viewset declaring neither `organization_scoped = True` nor a `GLOBAL_JUSTIFICATION` fails at import
- [ ] A viewset with `organization_scoped = True` and no `test_factory` fails at import
- [ ] `keel/core` imports nothing from `keel/organizations` — the Phase 0 import-linter contract stays green
- [ ] The baseline migration applies to an empty database, and `makemigrations --check` is clean immediately afterwards
- [ ] The baseline migration reverses cleanly, or the exception is named and justified
- [ ] UUIDv7 ids sort in creation order
- [ ] Cursor pagination is correct across a page boundary that falls inside a run of equal sort values
- [ ] `@audited` records on commit and registers; `@not_audited` registers with its reason; both are enumerable from the registry
- [ ] `crypto.py` round-trips, and a wrong key fails loudly
- [ ] `Decision.deny(reason, details)` reaches the client as a 403 whose envelope `code` is the reason and whose `details` is the details — provable now with a fixture guard, before Phase 3 registers any real one
- [ ] `has_perm` on an unregistered code raises rather than denying silently
- [ ] `pnpm lint`, `pnpm typecheck`, `pnpm test` pass; `uv run lint-imports` passes; `check_coverage.py` passes at the raised thresholds
- [ ] `manage.py check --deploy` under `config.settings.prod` produces no new error

---

## How to work

- **Strict TDD.** This is not scaffolding. Write the failing test, watch it fail, make it pass. That applies to the authz registry, the exception handler, pagination, the audit decorators, crypto, and the id generator. It does not apply to a model field declaration, where the test is the migration and the constraint.
- **Verify, do not assert.** Every acceptance box needs pasted command output.
- Get the models right before you get anything else right. A wrong column here costs three worktrees later.
- Update the Orca worktree comment at each task boundary:
  `orca worktree set --worktree active --comment "<short status>" --json`
- Commit in coherent chunks. The migrations go in one commit, together.
- Do not push, do not branch, do not open a PR. Work on `master`.
- Every commit message body ends with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AQXQvAv8g92xotjrnnibLc
```

## Report back

- Each acceptance box, pass or fail, with pasted evidence.
- **The membership-resolution seam**: how `OrgScopedViewSet` reaches organisation membership without importing `keel.organizations`, and what Phase 3 must do to wire it. Be precise — the next agent depends on this.
- Coverage thresholds you set, and why.
- Every decision the plan did not cover.
- Anything in `keel-prd.md` that looked wrong or unimplementable from inside the code, especially in the data model.
