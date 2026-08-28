#!/usr/bin/env bash
# Local mirror of the blocking CI gates, run by the `pre-push-gates` hook
# in .pre-commit-config.yaml. The repo
# runs on a free GitHub Actions plan, so catching a failure here — before
# it burns Actions minutes — is the whole point.
#
# Deliberately excluded (see docs/pre-push.md for the full rationale):
#   - `manage.py makemigrations --check`, `manage.py check --deploy`,
#     `lint-imports`, and the coverage gate (`check_coverage.py`) — none
#     is in phase-16.md 16.D's named list, and check-migrations/lint-imports
#     both need a working DB/settings import that not every push touches.
#   - The MFA-flag pytest rerun (`--ds=config.settings.test_mfa`) and
#     `--cov` — this is the "fast half" of pytest the plan asks for, not
#     the whole CI test-api job.
#   - e2e (Playwright), pnpm audit, pip-audit, gitleaks — slow, network-
#     or browser-dependent, or already scheduled/non-blocking in CI.
#
# Escape hatch: `git push --no-verify` skips this entirely. CI runs the
# full set regardless, so --no-verify trades a slower feedback loop for
# an unblocked push, not a bypassed gate.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

step() {
  printf '\n\033[1m▶ %s\033[0m\n' "$1"
}

step "ruff check"
(cd apps/api && uv run ruff check .)

step "ruff format --check"
(cd apps/api && uv run ruff format --check .)

step "mypy"
(cd apps/api && uv run mypy .)

step "check_permission_lint.py"
(cd apps/api && uv run python ../../scripts/check_permission_lint.py)

step "bandit"
(cd apps/api && uv run bandit -c pyproject.toml -r keel -x '*/tests/*,*/migrations/*')

step "eslint"
pnpm --filter web lint

step "prettier --check"
pnpm exec prettier --check .

step "build email templates (pytest dependency — see ci.yml's identical step)"
pnpm --filter @keel/emails build

step "pytest (fast subset: default settings, no coverage, no MFA-flag rerun)"
(cd apps/api && uv run pytest --no-cov -q)

step "merge_openapi.py drift"
(cd apps/api && uv run python ../../scripts/merge_openapi.py)
git diff --exit-code -- openapi.merged.json || {
  echo "openapi.merged.json is stale — run 'uv run python scripts/merge_openapi.py' from apps/api and commit the result." >&2
  exit 1
}

step "api-client generation drift"
(cd packages/api-client && pnpm generate)
git diff --exit-code -- packages/api-client/src/generated || {
  echo "packages/api-client/src/generated is stale — run 'pnpm --filter @keel/api-client generate' and commit the result." >&2
  exit 1
}

step "check_openapi_compat.py"
uv run --project apps/api python scripts/check_openapi_compat.py

printf '\n\033[1;32mAll pre-push gates passed.\033[0m\n'
