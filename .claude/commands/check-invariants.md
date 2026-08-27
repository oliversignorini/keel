Run every automated gate that enforces `CLAUDE.md`'s seven invariants, in
this order, and report pass/fail per gate mapped to the invariant it
covers. Run them for real — do not guess from reading code.

1. **Invariant 1 — domain purity.**
   `cd apps/api && uv run lint-imports`
   Fails if anything under `keel/domain/` imports Django, Celery, or a
   sibling app.

2. **Invariant 2 — permission placement.**
   `cd apps/api && uv run python ../../scripts/check_permission_lint.py`
   Fails if `Decision.allow(`, `Decision.deny(`, or `registry.register(`
   appears anywhere outside `keel/organizations/permissions.py` (test
   files exempt).

3. **Invariant 4 — schema changes are migrations.**
   `cd apps/api && uv run python manage.py makemigrations --check --dry-run`
   Fails if a model changed without a committed migration.

4. **Invariant 6 — tenant scoping.**
   `cd apps/api && uv run pytest keel/organizations/tests/test_meta_router_wiring.py keel/organizations/tests/test_tenant_isolation.py keel/organizations/tests/test_meta_guard_coverage.py -v`
   The first fails if a scoped viewset isn't reachable from the router.
   The second fails if cross-org access on any scoped viewset returns
   anything but 404. The third fails if a registered guard is missing an
   allow or a deny test.

5. **Invariant 7 — audit coverage and per-directory test coverage.**
   `cd apps/api && uv run pytest && python3 ../../scripts/check_coverage.py`
   pytest's own audit meta-test (`keel/audit/tests/`) fails on a mutating
   service decorated with neither `@audited` nor `@not_audited`.
   `check_coverage.py` fails naming every path under `[tool.keel.coverage]`
   in `apps/api/pyproject.toml` that missed its floor.

6. **Client drift — not a numbered invariant, but a hard CI gate.**
   `cd packages/api-client && pnpm generate && git diff --exit-code -- src/generated`
   Fails if the generated client is stale against `openapi.merged.json`.
   Run only if you changed a view, serializer, or route — this mutates
   `packages/api-client/src/generated`, and only one worktree at a time
   may regenerate it.

7. **Full lint pass** (ruff, mypy, eslint, prettier) —
   `cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy .`
   then from the repo root `pnpm --filter web lint && pnpm exec prettier --check .`

Report format: one line per gate — invariant number, command run, pass or
the exact failure. Do not silently fix a failure this command surfaces;
say what broke and let the caller decide, unless you were the one who just
generated the code being checked (e.g. `/new-resource` calling this at
the end), in which case fix it and re-run.

Invariants 3 (transaction boundary) and 5 (async tier boundary) have no
automated gate — call this out explicitly rather than silently skipping
them, and note that they were not checked.
