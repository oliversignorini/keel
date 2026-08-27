# Phase 10 handover — DRF → Django Ninja

Written mid-10.E, on explicit user instruction to stop before starting DRF
removal. All work below is committed on `oliversignorini/p10-ninja`. A
fresh agent should read `docs/plans/phase-10.md` and
`docs/adr/0001-django-ninja-over-drf.md` first — this file assumes both.

## Commits so far (in order)

1. `Phase 10.A: core Ninja primitives, mounted alongside DRF`
2. `Phase 10.B: migrate keel/widgets to Ninja, rewrite invariant meta-tests`
3. `Phase 10.C: migrate keel/audit to Ninja`
4. `Phase 10.C: migrate keel/billing to Ninja, add the plans cursor envelope`
5. `Phase 10.C: migrate keel/jobs to Ninja`
6. `Phase 10.C: migrate keel/files to Ninja`
7. `Phase 10.C: migrate keel/organizations to Ninja — 10.C complete`
8. `Phase 10.C: rename /api/v1/organizations/ to /api/v1/orgs/ (backend)`
9. `Phase 10.C follow-up: type every paginated list endpoint's OpenAPI schema`
10. `Phase 10.D: switch the OpenAPI pipeline to Ninja, regenerate the client`
11. `Phase 10.E: clean operation IDs, query params, and the apps/web sweep`

Full backend suite: 456 tests passing. `pnpm --filter web typecheck`,
`pnpm --filter web test` (127 tests), `pnpm --filter web lint`: all green.
ruff, mypy, `lint-imports`, and the per-directory coverage gate: all green.

## Stage status

- **10.A** — done. Core primitives in `keel/core/ninja_*.py`
  (auth, authz, pagination, throttle, exceptions, api). Cursor pagination
  ported line-for-line from DRF's `CursorPagination`, proven against
  ≥60 tied rows (`keel/core/tests/test_ninja_pagination.py`).
- **10.B** — done. `keel/widgets` migrated; `keel/organizations/tests/
  ninja_tenant_isolation.py` is the Ninja meta-test mechanism (walks
  `keel.core.ninja_authz.registered_scoped_resources()`, drives the real
  URL via Django's test `Client`, proven against a well-scoped/leaky
  fixture pair in `ninja_tenant_isolation_fixtures.py`). Abort-gate
  invariants proven by deliberately breaking each (see that commit body
  for the pasted failures) — **all three still bite with equal force**.
- **10.C** — done. All apps migrated: audit, billing (+ the plans cursor
  envelope, one of the three allowed changes), jobs, files, organizations
  (the intricate one — Me/permissions/invite-accept/transfer). The
  `/organizations/` → `/orgs/` rename (the second allowed change) is done
  across every backend route, `detail_url_template`, and test. 6 production
  `OrgScopedResource`s now exist and are all covered by the meta-test walk.
- **10.D** — done. `scripts/merge_openapi.py` reads
  `keel.core.ninja_api.api.get_openapi_schema()` instead of drf-spectacular.
  Deterministic (verified: run twice, byte-identical). **Real finding**:
  Ninja 1.6.3 hard-codes `"openapi": "3.1.0"` with real 3.1/JSON-Schema-2020-12
  shapes, no override exists. Verified empirically that orval 7.21 handles
  this fine — the one real gap (`nullable: true` beside a bare `$ref` in
  allauth's schema, `BaseAuthenticator.last_used_at`) is fixed by
  `_normalize_nullable_to_31()` in `merge_openapi.py`, which rewrites that
  3.0 pattern into 3.1's `anyOf`/`null` shape before merging. Client
  regenerated. Route-by-route diff walked (see that commit body): every
  path change is the orgs rename; 3 status-code "diffs" are drf-spectacular
  doc bugs being corrected (verified against the deleted DRF source before
  deletion — not behaviour changes); PUT was momentarily missing from two
  routes (DRF's `UpdateModelMixin` registered it) and has been restored
  with a test.
- **10.E** — partially done:
  - Every Ninja route got an explicit `operation_id=` (clean names:
    `listWidgets`, `createOrganization`, etc.) instead of Ninja's default
    module-path-derived name.
  - **Real gap found and fixed**: `list_widgets`/`list_jobs`/
    `list_audit_logs`/`list_members`/`list_roles`/`list_invitations`/
    `list_organizations`/`list_plans` read `cursor`/`limit` (and `status`
    for jobs) via `request.GET` internally but never declared them as
    function parameters, so Ninja's schema — and the generated client —
    had no typed way to request a page past the first. Fixed: all eight
    now declare the params explicitly.
  - All ~37 `apps/web` files referencing `@keel/api-client` fixed for the
    new operation IDs/type names (`WidgetOut`, `OrganizationOut`,
    `PageWidgetOut`, etc.). Several previously-untyped DRF `APIView`
    request bodies (checkout, transfer, uploads) now have real Ninja
    schemas, so wrapper functions pass the typed body directly instead of
    hand-building a `RequestInit` with `JSON.stringify`.
  - **Not done**: DRF removal (`rest_framework`/`drf-spectacular` still in
    `pyproject.toml`, `INSTALLED_APPS`, `REST_FRAMEWORK`/
    `SPECTACULAR_SETTINGS` settings, and `config/urls.py`'s
    `SpectacularAPIView` schema route).
  - **Not done**: Playwright e2e suites were fixed *statically* (the two
    specs' hardcoded `/api/v1/organizations/...` URLs → `/orgs/...`, per
    the rename) but never actually run — no attempt was made to bring up
    the docker-compose stack (Postgres/Redis/API/web) this session.
  - **Not done**: `apps/web/lib/org/types.ts`'s module docstring still
    narrates the DRF-era "drf-spectacular emits no response schema for
    these plain APIViews" reasoning. The types it defines are still
    correct and still needed (Ninja doesn't generate full response schemas
    for `me`/`permissions`/`invite_detail`/checkout/portal/subscription/
    credits either, since those Python views return bare `dict` with no
    `response=` schema declared) — only the *prose* is stale and should be
    rewritten to explain the Ninja-era reason instead of blaming DRF.

## Remaining work for 10.E (DRF removal) — a concrete plan

No production code depends on DRF anywhere anymore. What's left is genuinely
mechanical, but touches load-bearing `keel/core` modules and several meta-test
files, so budget real care and a full test run after each step.

1. **`keel/core/authz.py`**: delete `HasOrgPermission`, `GlobalViewSet`,
   `OrgScopedViewSet`, `registered_global_viewsets`,
   `registered_scoped_viewsets`, and the `rest_framework` imports. **Keep**
   `Decision`, `Guard`, `UnregisteredPermissionCode`, `PermissionRegistry`,
   `registry`, `has_perm`, and `_resolve_organization` — `keel/core/
   ninja_authz.py` imports `_resolve_organization` from this module
   directly; it has zero DRF dependency itself, just move/keep it.
2. **Delete `keel/core/pagination.py`** (DRF `CursorPagination` subclass —
   `keel/core/ninja_pagination.py` is the sole implementation now) and
   **delete `keel/core/authentication.py`** (DRF `SessionAuthentication`
   subclass — `keel/core/ninja_auth.py` replaces it).
3. **`keel/core/exceptions.py`**: stop `DomainError` inheriting
   `drf_exceptions.APIException` — make it a plain `Exception` subclass
   carrying `status_code`/`code`/`message`/`details` (it already has all
   four as instance attributes; only the base class changes, per the ADR's
   own framing). Delete `exception_handler`, `_envelope_parts`, and the DRF
   `_validation_details` (the Ninja one already lives separately in
   `keel/core/ninja_exceptions.py` — confirm nothing else imports the DRF
   one before deleting it).
4. **Settings** (`config/settings/base.py`): remove `"rest_framework"` and
   `"drf_spectacular"` from `INSTALLED_APPS`, delete the `REST_FRAMEWORK`
   dict, delete `SPECTACULAR_SETTINGS`. Keep
   `KEEL_API_THROTTLE_USER_RATE`/`_ANON_RATE` as real settings computed
   directly from `env(...)` (they currently read off the `REST_FRAMEWORK`
   dict — inline the two `env()` calls instead). Delete `KEEL_API_ROUTER`
   (its only purpose was the DRF meta-test walk — see step 7). Check
   `config/settings/test.py`'s `REST_FRAMEWORK = {**REST_FRAMEWORK, ...}`
   line — delete it; `KEEL_API_THROTTLE_USER_RATE = None` /
   `_ANON_RATE = None` already there and already sufficient.
5. **`config/urls.py`**: remove `from drf_spectacular.views import
   SpectacularAPIView` and the `/api/v1/schema/` path. Ninja's own
   `NinjaAPI` already serves `/api/v1/openapi.json` (and `/api/v1/docs`)
   automatically — verify this actually resolves before assuming it's a
   like-for-like replacement; if `apps/web` or anything else references
   `/api/v1/schema/` specifically, that needs its own fix.
6. **`apps/api/pyproject.toml`**: remove `djangorestframework` and
   `drf-spectacular` from `dependencies`; remove `rest_framework.*` from
   the mypy `ignore_missing_imports` override list (leave `allauth.*`,
   `boto3.*`, etc.); remove the `"keel/core/pagination.py" = 100` and
   `"keel/core/authentication.py" = 100` lines from
   `[tool.keel.coverage]` (files no longer exist) — consider adding
   `"keel/core/ninja_pagination.py" = 100` and
   `"keel/core/ninja_auth.py" = 100` in their place to preserve the
   *spirit* of the invariant (100% floors on load-bearing core security
   modules), not just satisfy the letter of "remove the dead entries." Run
   `uv lock` after editing dependencies.
7. **Meta-test files** — all of these test DRF machinery that no longer
   exists in production; their Ninja-side equivalents already exist and
   pass:
   - **Delete** `keel/core/tests/test_authz.py` (superseded by
     `test_ninja_authz.py`).
   - **Delete** `keel/core/tests/test_pagination.py` (superseded by
     `test_ninja_pagination.py`).
   - **Delete** `keel/core/tests/test_authentication.py` — but first
     **write a replacement** unit test for `keel/core/ninja_auth.py`
     (`session_auth`/`enforce_csrf`/`optional_session_auth`) directly —
     no such *unit-level* test currently exists; coverage today is only
     indirect, through endpoint tests using plain `Client()` (CSRF checks
     disabled by default) or `force_login`. This is a real, currently-open
     gap: nothing proves the CSRF-failure → 401 `authentication_failed`
     path against a *production* Ninja endpoint (the only place that was
     ever proven was the 10.A scratch endpoint, deleted in 10.B). Consider
     a small fixture-based test in the style of `test_end_to_end_denial.py`
     (see below) rather than deleting this gap silently.
   - **Delete** `keel/organizations/tests/tenant_isolation.py` (the DRF
     mechanism module — router-walk, `assert_cross_org_404` —
     superseded by `ninja_tenant_isolation.py`), and
     `keel/organizations/tests/test_tenant_isolation.py` (the meta-test
     built on it).
   - **`keel/organizations/tests/test_meta_router_wiring.py`**: remove the
     DRF-half test (`test_every_production_scoped_viewset_is_reachable_by_the_router`)
     and its now-dead imports (`OrgScopedViewSet`, `registered_scoped_viewsets`,
     `iter_org_scoped_viewsets`, `settings`, `import_string`) — **keep**
     `test_every_production_ninja_resource_is_reachable_by_the_router`.
   - **Delete** `keel/organizations/tests/test_end_to_end_denial.py` — it
     proves the DRF `OrgScopedViewSet` → guard → `Decision` →
     `PermissionDeniedWithReason` → envelope plumbing against fixture
     viewsets, explicitly "before p3-orgs-api's real viewset exists." The
     real thing exists now and is tested end to end
     (`test_api_organizations.py`'s role/state denial tests). Confirm the
     *state*-denial case (guard invoked with a `subject`, not just a role
     check) is still actually covered somewhere before deleting — skim
     `test_api_organizations.py::test_last_owner_cannot_be_removed_via_api`
     and `test_last_owner_cannot_be_demoted_via_api` first.
   - **Rewrite** `tests/test_rate_limiting.py` — it imports
     `rest_framework.throttling.AnonRateThrottle`/`UserRateThrottle`
     directly and cannot survive DRF's removal as-is. Rewrite against
     `keel.core.ninja_throttle.AnonRateThrottle`/`UserRateThrottle`
     instead, same shape (subclass with an explicit low `rate=` to bypass
     settings, same three assertions: anon 429+Retry-After, user
     429+Retry-After, two users don't share a bucket). The acceptance
     criterion says this file "passes unchanged" — that's satisfied in
     spirit (same guarantees, same assertions) but not literally, since
     the DRF import has to go; say so plainly in the final report rather
     than quietly rewriting and claiming literal compliance.
   - **Delete** `keel/organizations/urls.py` once `KEEL_API_ROUTER` is gone
     (its only remaining content, `api_registry`, has no reader left) —
     confirm nothing else imports it first (`grep -rn
     "organizations.urls\|organizations import urls" apps/api`).
8. **`keel/core/conftest.py` / `keel/organizations/tests/conftest.py`**:
   the CI justification print
   (`pytest_terminal_summary`) currently walks both
   `keel.organizations.tests.tenant_isolation.iter_global_justifications`
   (DRF) and `keel.organizations.tests.ninja_tenant_isolation`'s Ninja
   counterpart. Once the DRF one is deleted, drop that half — walk only
   the Ninja registry.
9. **Verify**: `grep -rn "rest_framework" apps/api` must return nothing.
   Full backend suite green. `uv run mypy .`, `uv run lint-imports`,
   `uv run python scripts/check_coverage.py` (from `apps/api`, pointing at
   `../../scripts/check_coverage.py`) all green. Regenerate
   `openapi.merged.json` and the client one more time after DRF removal —
   `drf-spectacular`'s absence shouldn't change the merged document at all
   (Ninja's schema was already the only `/api/v1/...` input since 10.D),
   but confirm the diff is empty rather than assuming it.
10. Update `docs/review-2026-08.md`-adjacent CI docs if any step in
    `.github/workflows/ci.yml` names DRF — grep confirmed **no matches**
    as of this handover, so this is likely a no-op, but re-check after any
    of the above changes touch `apps/api/pyproject.toml`.

## Known gotchas (learned the hard way this session — don't rediscover)

- **Route registration order matters.** Django resolves URL patterns by
  path regex before Ninja ever looks at HTTP method. A catch-all
  `{id}`/`{pk}` route registered *before* a literal sibling route (e.g.
  `/widgets/echo/`) claims that literal path first and answers 405/wrong-
  type instead of falling through. Always register literal paths before
  parameterized ones on the same router.
- **`response=Page[XOut]` + pre-serializing rows is double-serialization.**
  `keel/core/ninja_pagination.py`'s `paginate()` must return *raw ORM rows*
  in `results`, not pre-built dicts — Ninja serializes each row itself
  against the declared `response=` schema, running `resolve_*` methods
  against the real ORM instance. A resolver like `resolve_created_by`
  reads `obj.created_by_id`, which doesn't exist on an already-built dict
  keyed by the schema's own output field names.
- **`CursorPaginator` always re-orders by its own `ordering`.** A queryset
  built with its own `.order_by(...)` gets silently overridden by the
  paginator's default `(-created_at, id)` unless `paginate(request,
  queryset, ordering=(...))` is passed explicitly. Bit `GET /api/v1/plans/`
  (needs `(sort_order, code)`) — caught by a flaky-looking test failure
  that only reproduced when run alongside other tests in the same file.
- **Ninja list endpoints only expose query params it sees in the function
  signature.** Reading `request.GET.get("cursor")` inside the body (which
  `CursorPaginator` does internally) doesn't make Ninja document or
  generate a typed parameter for it — declare `cursor: str | None = None`
  etc. explicitly on every list route, even though the paginator ignores
  the declared value and re-reads `request.GET` itself.
- **django-ninja 1.6.3 hard-codes OpenAPI 3.1** (`ninja/openapi/schema.py`)
  with no override — don't waste time looking for a settings flag. Verify
  orval compatibility empirically rather than assuming; it was fine except
  for the one `nullable`+`$ref` pattern documented above.
- **All django-ninja views are `csrf_exempt` at the Django middleware
  level always** (`ninja/operation.py`, "Cookie-based auth (APIKeyCookie)
  handles CSRF checking separately") — `keel/core/ninja_auth.py`'s own
  `enforce_csrf()` (built on `CsrfViewMiddleware` directly) is the *only*
  CSRF protection Ninja routes get. This was a deliberate 10.A design
  decision, not an oversight — don't "fix" it by turning on some Ninja
  CSRF flag, there isn't one for plain auth callables and Ninja's built-in
  mechanism for its own auth classes answers 403 instead of the 401 the
  invariant requires.
- **DRF's `PrimaryKeyRelatedField` resolved an id to a model instance
  during validation; Ninja's typed `role_id: UUID` field only validates
  shape.** Anywhere a DRF serializer took `role_id`/similar and the
  service function expects a real instance, add an explicit
  `_get_role_or_422`-style lookup (see `keel/organizations/views.py`) —
  don't pass the raw id straight through.
- **First-ever Ninja request in a process costs ~450ms** (pydantic/OpenAPI
  schema compilation); 2nd+ costs ~7ms. A few timing-sensitive tests
  (`test_create_job_returns_202_quickly_with_the_work_not_yet_started`)
  are only sensitive to this when run in total isolation as the very first
  test of a fresh process — the full suite (CI's actual invocation, no
  xdist) already warms this up. Don't weaken the threshold; it passes
  under the invocation that matters.
- **Windows/Git-Bash `/tmp` path quirk**: `/tmp/foo.json` written by one
  Bash tool call may not be visible to a Python subprocess in a later
  call (MSYS path virtualization). Use real Windows-relative paths in the
  repo (or the scratchpad dir under `C:\Users\...\AppData\Local\Temp\...`)
  for anything that needs to survive across a Bash→Python handoff.

## Verification commands (from `apps/api/`)

```
uv run pytest -q                                  # full backend suite + coverage
uv run python ../../scripts/check_coverage.py     # per-directory floors
uv run ruff check .
uv run mypy .
uv run lint-imports
uv run python ../../scripts/merge_openapi.py      # regenerate openapi.merged.json
git diff --exit-code -- ../../openapi.merged.json # determinism / staleness check
```

From the repo root:

```
pnpm --filter web typecheck
pnpm --filter web test
pnpm --filter web lint
pnpm --filter @keel/api-client generate            # regenerate the TS client (from packages/api-client)
```

None of the above requires a running Postgres/Redis for the pure-Python
checks other than `uv run pytest` itself, which needs the same local
Postgres this repo's `apps/api` test settings already assume (see
`config/settings/test.py`'s docstring). Playwright (`apps/web/e2e/`) needs
the full docker-compose stack up and was not attempted this session.
