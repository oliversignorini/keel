# Local pre-push gates

`docs/plans/phase-16.md` 16.D. The repo runs CI on GitHub's free plan, so
the answer to "this failure should be caught earlier" is a local hook,
not another Actions job. `git push` now runs a mirror of the blocking CI
gates before anything reaches GitHub; a broken push never burns Actions
minutes in the first place.

## Setup

One-time, per clone:

```bash
uvx pre-commit install --hook-type pre-commit --hook-type pre-push
```

(or `pip install pre-commit` / `pipx install pre-commit` first, then
`pre-commit install --hook-type pre-commit --hook-type pre-push`, if
you don't have `uv`/`uvx`.) This installs two separate git hooks from
the one `.pre-commit-config.yaml`:

- **pre-commit** (unchanged from Phase 0): ruff, ruff-format, mypy,
  prettier, eslint, end-of-file-fixer, trailing-whitespace,
  check-merge-conflict — fast, changed-files-only, runs on every commit.
- **pre-push** (this phase): one hook, `pre-push-gates`, that runs
  `scripts/pre-push-checks.sh` against the whole repo.

## Why pre-commit, not lefthook

Both are reasonable choices; pre-commit won because the repo already had
a `.pre-commit-config.yaml` from Phase 0 (`docs/plans/phase-0.md` 0.7) —
adding lefthook alongside it would mean two hook managers, two install
steps, and two places a new contributor could look and find nothing.
pre-commit's `stages:` key maps directly onto "some hooks run at commit,
some at push" without a second config file, and its `repo: local` hook
type lets the push-time gates shell out to the project's own `uv run` /
`pnpm` commands instead of a pre-commit-managed environment — which
matters here specifically: fixing this phase's other finding (see
below) showed that pre-commit's own isolated per-hook environments had
been silently wrong for mypy and eslint since Phase 0, because they
didn't share the real `apps/api/.venv` or `apps/web`'s
`@keel/eslint-config` workspace package. Running the project's actual
tools instead of a shadow toolchain is what makes the pre-push mirror
trustworthy in the first place.

## What the pre-push hook runs

In order (`scripts/pre-push-checks.sh`), ~50s warm on the machine this
was built on:

1. `ruff check` / `ruff format --check` (apps/api)
2. `mypy` (apps/api)
3. `scripts/check_permission_lint.py`
4. `bandit`
5. `eslint` (`pnpm --filter web lint`)
6. `prettier --check`
7. build email templates (pytest dependency, same as CI's `test-api` job)
8. `pytest --no-cov -q` (apps/api) — the *fast subset* of CI's `test-api`
   job, see below
9. `merge_openapi.py`, diffed against the committed `openapi.merged.json`
10. `pnpm --filter @keel/api-client generate`, diffed against the
    committed `packages/api-client/src/generated`
11. `scripts/check_openapi_compat.py` (additive-only compat gate — see
    that script's docstring)

## What "fast subset" means for pytest

Step 8 is `apps/api`'s default `pytest` run, same settings module
(`config.settings.test`) as CI, just without `--cov` (coverage
instrumentation costs real time for a check nobody reads locally — CI's
`check_coverage.py` still gates on it) and without the second,
`--ds=config.settings.test_mfa` run CI does for the MFA-flag acceptance
test. That second run exists to prove one thing (TOTP endpoints appear
under a different settings module) and re-boots Django under a whole
separate settings module to do it — not worth doubling local push time
for.

## What's deliberately excluded entirely

- `manage.py makemigrations --check --dry-run` and `manage.py check
  --deploy` — not named in 16.D's gate list, and `check --deploy` needs
  `config.settings.prod` plus placeholder env vars CI sets explicitly
  (see `ci.yml`'s `test-api` job); wiring that locally for a check that
  only matters at merge time isn't worth the noise.
- `lint-imports` (the `contracts` job's import-linter check) — same
  reasoning, not in 16.D's list.
- `check_coverage.py` — needs the `--cov` run this hook skips (see
  above), and per-directory coverage regressions are a merge-time
  concern, not a per-push one.
- Playwright e2e (`accessibility.spec.ts`, `auth-flows.spec.ts`),
  `pnpm audit`, `pip-audit`, `gitleaks` — slow, browser- or
  network-dependent, or already scheduled/non-blocking in CI
  (`security.yml`). None of these gate a merge on every push today; they
  don't need to gate one locally either.

## Escape hatch

```bash
git push --no-verify
```

skips the pre-push hook entirely. CI runs the full set of gates
regardless — `--no-verify` trades a slower feedback loop (find out on
GitHub instead of locally) for an unblocked push, not a bypassed gate.
Reach for it when you know a gate is failing for a reason unrelated to
your change (e.g. a flaky local Postgres) and want CI's clean-environment
result instead.

## A bug this phase found and fixed along the way

Phase 0's `.pre-commit-config.yaml` had never actually been run
end-to-end: `pre-commit/mirrors-prettier`'s pin (`v3.3.3`) doesn't exist
in that repo (it stopped tagging real releases after `v3.1.0`), and the
`mirrors-mypy` / `mirrors-eslint` hooks both failed on every real
invocation (`mypy: error: Missing target module...` and `ESLint
couldn't find an eslint.config file`, respectively — the former from
`pass_filenames: false` with no explicit target, the latter from running
outside `apps/web` with an isolated `additional_dependencies: [eslint]`
that can't see `@keel/eslint-config`). Fixed as part of standing this
phase's pre-push layer up far enough to verify it locally: prettier now
points at `rbubley/mirrors-prettier` (the community-maintained
continuation), and mypy/eslint are `repo: local` hooks that shell out to
`apps/api`'s real `uv run mypy .` and `pnpm --filter web lint` — the
same commands CI runs.
