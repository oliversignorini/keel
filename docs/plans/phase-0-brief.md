# Phase 0 — agent brief

You are implementing **Phase 0** of Keel, a Django 6 + Next.js 15 SaaS template. You are working directly on `master` in this checkout — not a worktree, not a branch.

## Read these first, in full, before writing anything

1. **`docs/plans/phase-0.md`** — your task list. Authoritative for scope. It has an explicit out-of-scope table. Work it task by task, 0.1 through 0.12.
2. **`keel-prd.md`** — the product requirements, v1.2. Read at minimum: §4 "Repository layout", §4 "Django app layout", §4 Architecture Invariants (especially invariant 7 on per-directory coverage and the `keel/domain/` contract), §5 "Token contract", §8 "Phase 0", and the Appendix dependency manifest. Skim the rest so you understand what you are building the box for.

Where the plan and the PRD disagree, **the PRD wins and you report the conflict.**

## Non-negotiables

- **Stay inside Phase 0.** No Django models. No migrations. No `keel/core/authz.py`, `audit.py`, `tasks.py`, base viewsets, exception handler or pagination — those are Phase 1 and another agent owns them. No allauth, Stripe, Sentry, drf-spectacular, boto3 or resend. No UI components. If an acceptance criterion appears to need one of those, stop and report it as a plan bug rather than building it.
- **Do not create `keel/domain/`.** The import-linter contract must be provably inert while that directory is absent.
- **Do not edit `keel-prd.md` or anything under `docs/plans/`.**
- **Verify, do not assert.** Every acceptance checkbox in the plan needs pasted command output. "Should work" is not a result. Run the commands. If something fails on Windows, report exactly what failed and what you did instead — that is useful information about the template, not a failure on your part.
- Two things must be proved by deliberately breaking them and showing the failure output:
  1. the import-linter contract — add a file under `keel/domain/` that imports the ORM, watch the contract fail, delete it, watch the contract go silent again;
  2. the coverage gate — `scripts/check_coverage.py` must fail both on an under-threshold path and on a glob that matches nothing.
- **`uv` is not installed on this machine.** Installing it is task 0.1.
- Docker is available. Start `infra/compose.dev.yml` services when you need them — you will, to run pytest against a real Postgres.
- **Do not push. Do not open a PR. Do not create branches.** Work on `master`.
- Commit in coherent chunks with real messages as you go, not one commit at the end. End every commit message body with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AQXQvAv8g92xotjrnnibLc
```

## Keep the orchestrator informed

Update the Orca worktree comment at each meaningful checkpoint so progress is visible without reading your transcript:

```
orca worktree set --worktree active --comment "<short status>" --json
```

Do this after finishing each numbered task, and immediately if you become blocked.

## Working style

Strict TDD does not apply to scaffolding — write the config, then write the test that proves the config does what it claims. But nothing counts as done until you have run it.

If you hit an ambiguity the plan does not cover, make the obvious call, note it, and keep going. Stop only for something that would be wrong to guess at.

## Report back, in the terminal, when done

- Each acceptance checkbox from `docs/plans/phase-0.md`, marked pass or fail, with pasted evidence.
- Every decision you made that the plan did not cover, and why.
- Anything in `keel-prd.md` that looked wrong or unimplementable from inside the code. This is valuable and I want it.
- Anything Windows-specific that did not work as the plan assumed.
- The list of commits you made.
