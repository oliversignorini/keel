# CLAUDE.md

Keel is a Django 6 + Next.js 15 SaaS template. Full detail lives in
`docs/architecture.md` (the seven invariants, request path, type
synchronisation) and `keel-prd.md` §4; this file is the short version an
agent needs before writing a line here.

## Per-app file shape

Every domain app under `apps/api/keel/` follows the same seven files.
`apps/api/keel/widgets/` is the reference slice — copy its shape, not its
content.

```
<app>/
├── models.py         # data shape only
├── services.py       # ORM, transactions, side effects — ALL writes
├── selectors.py       # ALL reads
├── permissions.py     # required permission codes (organizations app only — see below)
├── serializers.py     # shape validation at the edge
├── views.py           # THIN: parse, call service, serialize, return
├── tasks.py            # one-line delegations to services
└── tests/
```

A view, serializer, Celery task, admin page, or management command that
contains a business rule is a bug, not a style choice.

## The seven invariants

| #   | Invariant                                                                                                                                                                                                                                                 | Enforced by                                                                                                                                                                                                  | Verify with                                                                                                                          |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Domain logic lives in `services.py`/`selectors.py`, never views/serializers/tasks/admin. Optional pure layer in `keel/domain/` may never import Django, Celery, or `keel/*`.                                                                              | `import-linter` contract in `apps/api/pyproject.toml` (`[[tool.importlinter.contracts]]`) — inert until `keel/domain/` has a file in it                                                                      | `cd apps/api && uv run lint-imports`                                                                                                 |
| 2   | Authorization is expressed only in `keel/organizations/permissions.py` (`Perm` codes + `has_perm`/`registry.register`). `keel/core/authz.py` holds only the `Decision` type and registry — no rules. Services call `has_perm`, never reimplement a check. | `scripts/check_permission_lint.py` greps for `Decision.allow(`/`Decision.deny(`/`registry.register(` outside the sanctioned file                                                                             | `cd apps/api && uv run python ../../scripts/check_permission_lint.py`                                                                |
| 3   | One `transaction.atomic()` per service function, opened in the service, never the view. Calls to Stripe go through `transaction.on_commit()`, never inside an open transaction.                                                                           | Code review — no automated gate                                                                                                                                                                              | —                                                                                                                                    |
| 4   | Schema changes are Django migrations only — no admin/dashboard/console schema edits. Currently one baseline migration per app.                                                                                                                            | CI's `makemigrations --check --dry-run`                                                                                                                                                                      | `cd apps/api && uv run python manage.py makemigrations --check --dry-run`                                                            |
| 5   | Async work: Tier 1 (fire-and-forget) goes through the `keel/core/tasks.py` shim; Tier 2 (multi-step, resumable) uses Celery directly, as `keel/jobs/` does.                                                                                               | Code review — no automated gate                                                                                                                                                                              | —                                                                                                                                    |
| 6   | Every viewset declares `organization_scoped = True` + `test_factory`, or `organization_scoped = False` + `GLOBAL_JUSTIFICATION`. Cross-org access on a scoped viewset returns 404, not 403.                                                               | `OrgScopedViewSet.__init_subclass__` (`keel/core/authz.py`) fails at import if neither is present; `keel/organizations/tests/test_meta_router_wiring.py` walks the router; `tenant_isolation.py` asserts 404 | `cd apps/api && uv run pytest keel/organizations/tests/test_meta_router_wiring.py keel/organizations/tests/test_tenant_isolation.py` |
| 7   | Every mutating service is `@audited("action.name")` or `@not_audited(reason=...)`. Coverage is gated per directory (`[tool.keel.coverage]` in `apps/api/pyproject.toml`), not by one global number.                                                       | `keel/audit` meta-test fails on a service decorated with neither; `scripts/check_coverage.py` reads `coverage.json` after pytest                                                                             | `cd apps/api && uv run pytest && python3 ../../scripts/check_coverage.py`                                                            |

## Other things that will bite you

- `packages/api-client/src/generated` is never hand-edited. It is produced
  by `pnpm --filter @keel/api-client generate` (orval, reading
  `openapi.merged.json`, itself produced by `scripts/merge_openapi.py`
  from the DRF and allauth specs). CI's `api-client-generation` and
  `contracts` jobs both fail on drift — regenerate and commit, don't
  patch the output.
- Only one worktree at a time regenerates `openapi.merged.json` or the
  generated client. Two in flight is an unresolvable merge conflict.
- No migrations outside a phase that declares one — see `docs/review-2026-08.md`.
- **ADR 0001 replaces DRF with Ninja in Phase 10.** The commands below and
  the invariant table above describe today's DRF reality. Read
  `docs/adr/0001-django-ninja-over-drf.md` before assuming a pattern here
  survives that migration.

## Use Django first

Auth (django-allauth headless), pagination (`keel/core/pagination.py`),
caching, email (`keel/notifications/`), file storage (`keel/files/`),
management commands, deploy checks (`manage.py check --deploy`) and
storage abstractions are already solved by Django or by an app in this
repo. Reinventing one of these instead of extending the existing seam
makes the template worse for the next project that instantiates it.

## Before you open a PR

Run `/check-invariants`. It maps every gate above to the invariant it
covers.
