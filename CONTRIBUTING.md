# Contributing

Keel is a solo-maintained SaaS template (`CHANGELOG.md` has the full phase
history). External contributions are welcome, but the invariants below are
not up for discussion in a PR — they are load-bearing and mostly enforced
by CI.

## Getting the dev environment up

Follow the README's Quick start, then `docs/dev-setup.md` for the
`lvh.me` subdomain routing and login flow. Don't duplicate those steps here;
if they're wrong, fix them there.

## What CI enforces

Every PR runs (`.github/workflows/ci.yml`):

- **`lint`** — ruff, mypy, `check_permission_lint.py`, eslint, prettier
- **`typecheck`** — tsc across `apps/web` and `packages/api-client`
- **`test-api`** — `makemigrations --check --dry-run`, pytest (including an
  MFA-enabled run), then `scripts/check_coverage.py`'s per-directory
  coverage floors
- **`test-web`** — vitest for `apps/web` and `packages/api-client`
- **`api-client-generation`** — regenerates the TypeScript client from the
  OpenAPI spec and fails if `packages/api-client/src/generated` is stale
- **`e2e-accessibility`** — Playwright + `axe-core` over auth and account
  routes
- **`contracts`** — `lint-imports` (the `keel/domain` and `keel/core`
  import contracts) and re-derives `openapi.merged.json`, failing on drift

Every PR also runs (`.github/workflows/generators.yml`), not path-filtered
since a change to shared authz/permission code can break every future
generated slice:

- **`templates-lint`** — ruff over `templates/`, and asserts no
  template-engine syntax crept in
- **`reference-slice-is-a-render`** — regenerates `apps/api/keel/widgets`
  and its frontend route from `templates/resource`/`templates/ui` and
  fails on any diff against what's committed
- **`generated-slice-passes-the-invariants`** — generates a throwaway
  resource, readonly-resource, permission, and email into the CI checkout
  and runs the full invariant suite against them

If you're adding a resource, permission, job, or email, use `pnpm gen`
(see CLAUDE.md's generator catalogue) rather than hand-copying
`apps/api/keel/widgets/` — that directory is a generated render, not a
template to copy by hand, and CI's `reference-slice-is-a-render` job will
reject drift between it and `templates/resource`.

## Invariants a PR must not break

These are the seven architecture invariants from `docs/architecture.md`,
restated as things a reviewer (human or CI) will actually check. That
file has the full explanation and names what enforces each one.

1. **Domain logic lives in `services.py` / `selectors.py`.** Views,
   serializers, Celery tasks, admin, and management commands call into
   services — they don't contain business rules.
2. **Authorization lives in `organizations/permissions.py`, and nowhere
   else.** A new viewset declares its `_ACTION_PERMISSIONS` and either
   `organization_scoped = True` plus a `test_factory`, or a
   `GLOBAL_JUSTIFICATION` paragraph. Every guard needs an allow test and a
   deny test, and the deny test must assert the `reason`, not just that
   access was refused. `keel/core/authz.py`'s `__init_subclass__` hook and
   `keel/organizations/tests/test_meta_router_wiring.py` fail the build if
   any of this is missing.
3. **One `transaction.atomic()` per service function, opened in the
   service.** External calls (Stripe, etc.) go out via
   `transaction.on_commit()`, never from inside an open transaction.
4. **Schema changes are migrations, reviewed, in version control.** No
   dashboard or admin-console schema edits. A migration in a feature PR
   that isn't Phase 9–18's declared schema work is drift — say why in the
   PR description.
5. **Async work goes through the Tier 1 shim (`keel/core/tasks.py`) or
   Celery directly (Tier 2), per the PRD's criteria** — not a bespoke
   background-thread pattern.
6. **Validation is two layers: serializers at the HTTP edge, services for
   invariants.** Client-side Zod (generated from the OpenAPI spec) is UX
   only, never enforcement.
7. **Every mutating service is `@audited(action)` or
   `@not_audited(reason=...)`.** A meta-test fails on anything decorated
   with neither.

Two more, checked mechanically rather than by review:

- **`packages/api-client/src/generated` is never hand-edited.** If the API
  changed, regenerate it (`pnpm --filter @keel/api-client generate` from
  the repo root, or see `packages/api-client/package.json`) and commit the
  diff — the `api-client-generation` CI job will otherwise fail on drift.
- **Tests cover both the allow path and the deny path**, not just the
  happy path — this is what the coverage floors in
  `apps/api/pyproject.toml`'s `[tool.keel.coverage]` are shaped to catch.

## Commit and PR expectations

- One coherent unit of work per commit, not one commit per file.
- Fill in the PR template's checklist honestly — an unchecked box with a
  one-line reason is more useful than a checked box that isn't true.
- If you're touching `apps/api`, run `uv run pytest` and
  `uv run lint-imports` locally before pushing; both are slow enough in CI
  that a broken run wastes a cycle.
