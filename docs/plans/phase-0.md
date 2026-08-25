# Phase 0 — Repository and toolchain

**Owner:** one Sonnet agent, working directly on `master` in the primary working directory.
**Source of truth:** `keel-prd.md` v1.2, Phase 0 (§8) plus §4 "Repository layout", "Django app layout" and invariant 7.
**Size:** Small. This phase creates no models, no business logic, and no features.

---

## Boundary — read this before anything else

Phase 0 builds the box. Phase 1 puts things in it.

**In scope:** workspace wiring, dependency manifests, container services, linting, type checking, test runners, CI, and the smallest Django and Next.js projects that can genuinely start, hot-reload, and be tested.

**Out of scope — do not write these, another agent owns them:**

| Thing | Owner |
|---|---|
| Any Django model, any migration | Phase 1 (baseline migration) |
| `keel/core/authz.py`, `audit.py`, `tasks.py`, base viewsets, exception handler, pagination | Phase 1 |
| DRF configuration beyond installing it, drf-spectacular wiring | Phase 1 |
| allauth, Celery task definitions, Stripe, any app under `keel/` other than empty packages | Phases 2–4 |
| Any UI component, any route beyond a single placeholder page | Phases 2–6 |
| `keel-prd.md`, anything under `docs/plans/` | The orchestrator |

If a Phase 0 acceptance criterion appears to require something from the table above, stop and report it rather than building it. That is a plan bug, and it is worth more as a question than as code.

---

## Environment facts, already verified on this machine

- Node 25.6.0, pnpm 9.5.0 — both above the floor (Node 22).
- Python 3.12.4 — meets the floor.
- Docker 29.7.2 and `gh` 2.96.0 available.
- **`uv` is not installed.** Installing it is task 0.1.
- Platform is Windows 11. Git reported an LF→CRLF conversion warning on the first commit, so `.gitattributes` is not optional here.

---

## Tasks

Work them in order. Each names the files it creates and finishes with something runnable.

### 0.1 — Toolchain prerequisites

- Install `uv` (`winget install --id=astral-sh.uv`, or the official standalone installer). Verify `uv --version`.
- Create `.gitattributes` at the repo root: `* text=auto eol=lf`, with `*.ps1`, `*.bat`, `*.cmd` forced to `crlf`. Commit it before generating any other file so nothing lands with mixed endings.
- Create `.editorconfig`: LF, UTF-8, final newline, 4-space Python, 2-space everything else.

**Done when:** `uv --version` prints, both files are committed, and `git add` on a new text file produces no CRLF warning.

### 0.2 — Workspace skeleton

Create the layout from §4 of the PRD:

```
apps/api/  apps/web/
packages/{ui,api-client,eslint-config,tsconfig}/
infra/  scripts/  docs/  .github/workflows/  .claude/{commands,skills}/
```

Files:
- `pnpm-workspace.yaml` — `apps/*`, `packages/*`
- `package.json` (root) — private, `packageManager` pinned to the installed pnpm, scripts delegating to turbo: `dev`, `build`, `lint`, `typecheck`, `test`
- `turbo.json` — pipeline for `dev` (persistent, uncached), `build`, `lint`, `typecheck`, `test`
- `.npmrc` — `engine-strict=true`
- `.gitignore` — Python, Node, Next, Django, coverage, `.env`, `.venv`, `.turbo`

**Done when:** `pnpm install` completes and `pnpm turbo run lint --dry-run` resolves the graph without error.

### 0.3 — Shared TS config and lint packages

- `packages/tsconfig/` — `base.json`, `nextjs.json`, `react-library.json`, published as `@keel/tsconfig`. **TS strict, and `noUncheckedIndexedAccess` on.**
- `packages/eslint-config/` — flat config as `@keel/eslint-config`, exporting a base and a Next variant. Prettier at the root (`.prettierrc`), with Prettier disabling conflicting ESLint rules.

**Done when:** both packages resolve from `apps/web` by name.

### 0.4 — `apps/web`: Next.js 15 skeleton

- Next.js 15, App Router, React 19, TypeScript strict, Tailwind v4.
- One route only: `app/page.tsx` rendering a placeholder. Do not create route groups; Phases 2–7 own those.
- `next.config.ts`, `tsconfig.json` extending `@keel/tsconfig/nextjs.json`, `eslint.config.mjs` extending `@keel/eslint-config`.
- Vitest with `@testing-library/react` and jsdom. **One real test** — a trivial pure utility in `lib/` plus its test — so `pnpm test` is not vacuous.
- Scripts: `dev`, `build`, `lint`, `typecheck`, `test`, `test:coverage`.

**Done when:** `pnpm --filter web dev` serves with hot reload; `typecheck` and `test` pass.

### 0.5 — `packages/ui` and `packages/api-client` stubs

- `packages/ui` — package with `theme.css` carrying the full token contract from §5 of the PRD: OKLCH, light and dark, declared on `:root, [data-theme]` and `.dark, [data-theme][data-mode="dark"]` per the PRD's nestable-selector requirement. No components yet.
- `packages/api-client` — stub with a `README.md` stating it is generated and never hand-edited, and a `.gitattributes` marking it `linguist-generated`. No orval config yet; the OpenAPI spec does not exist until Phase 1.

**Done when:** both typecheck clean and `theme.css` imports into `apps/web`.

### 0.6 — `apps/api`: Django 6 skeleton with `uv`

- `pyproject.toml` managed by `uv`, `requires-python = ">=3.12"`, Django `~=6.0`.
- **Dependencies at this phase only:** django, djangorestframework, django-cors-headers, psycopg[binary], celery, redis, uuid-utils, and one env-config library (pick django-environ or python-decouple and record why). Dev: pytest, pytest-django, pytest-cov, ruff, mypy, django-stubs, import-linter, factory-boy. Do **not** install allauth, stripe, boto3, resend, sentry-sdk or drf-spectacular — later phases add those alongside the code that uses them.
- `config/settings/{base,dev,prod,test}.py` — split settings reading from env. Base declares `INSTALLED_APPS` with Django contrib plus DRF and corsheaders only, `DATABASES` pointing at the compose Postgres, `CACHES` and the Celery broker at the compose Redis, and the version-floor assertions. `test` uses a real Postgres, not sqlite — the tenant-isolation and ledger tests later depend on Postgres semantics, and switching test backends mid-build is a trap.
- `config/urls.py` — `/healthz/` returning 200 with no DB access, and `/readyz/` that does touch the DB and Redis. Nothing else.
- `config/celery.py`, `config/asgi.py`, `config/wsgi.py`, `manage.py`.
- `keel/__init__.py`, and empty packages `keel/{core,accounts,organizations,billing,audit,notifications,files,widgets}/`, each with `__init__.py` and `apps.py`, **registered in `INSTALLED_APPS` and containing no models.** They exist so Phase 1's baseline migration has somewhere to land.
- `keel/domain/` — **do not create this directory.** The import-linter contract must be inert while it is absent, and proving that is an acceptance criterion.
- `tests/` with one real test hitting `/healthz/` through the Django test client.

**Done when:** `uv run python manage.py check` passes, `uv run pytest` passes against the compose Postgres, and `runserver` hot-reloads.

### 0.7 — Lint, types, import contracts

- Ruff: line length 100, target py312, rules including `E`, `F`, `I`, `UP`, `B`, `DJ`, `RUF`. Format with ruff.
- Mypy: `disallow_untyped_defs`, `warn_return_any`, `no_implicit_optional`, `django-stubs` plugin wired to `config.settings.test`.
- import-linter with **two** contracts:
  1. `keel.domain` is independent — forbidden from importing `django`, `celery`, `config`, or any `keel.*` outside itself.
  2. `keel.core` must not import `keel.organizations` (PRD v1.2, Phase 1 acceptance). Declare it now; it is trivially satisfied while both are empty and becomes load-bearing in Phase 1.
- Both contracts must be **silent while their subject packages are empty or absent** and must fail when violated. Prove it — see acceptance.
- `.pre-commit-config.yaml` — ruff, ruff-format, mypy, prettier, eslint, end-of-file-fixer, trailing-whitespace, check-merge-conflict.

**Done when:** `pnpm lint`, `pnpm typecheck` and `uv run lint-imports` all pass.

### 0.8 — Per-directory coverage gate

The one piece of real engineering in Phase 0. PRD v1.2, §4 invariant 7 specifies it.

- `[tool.keel.coverage]` in `apps/api/pyproject.toml`: a mapping of path glob to required percentage. Seed it from the PRD's table, with paths that do not exist yet omitted — Phase 1 onward adds them as the code arrives.
- `scripts/check_coverage.py`: runs after pytest against `coverage.json`. Exits non-zero naming every path that missed, with actual and required figures. A path matched by no glob is **reported and does not fail**. A glob matching no path **does fail** — a renamed directory that leaves its obligation behind is exactly the failure this catches.
- Wire it into the api workspace's `test` script and into CI.

**Done when:** it passes on the current tree; adding an untested function makes it fail with a readable message; adding a glob for a nonexistent path makes it fail.

### 0.9 — `infra/compose.dev.yml`

- Postgres 17 with pgvector available (`pgvector/pgvector:pg17` or equivalent — the PRD requires `CREATE EXTENSION vector` to succeed on the dev image), Redis 7, Mailpit. **Nothing else** — no API container, no worker. The API runs natively.
- Named volumes, healthchecks on all three, ports 5432 / 6379 / 1025 + 8025.
- `infra/compose.prod.yml` — create the file with API, worker and beat services sketched and a comment naming the phase that finishes it. An absent file gets forgotten; a stub with a TODO does not.

**Done when:** `docker compose -f infra/compose.dev.yml up -d` brings all three healthy and nothing else.

### 0.10 — `.env.example` and `pnpm dev`

- `.env.example` documenting every variable the code currently reads, each with a comment. No secrets, no real values.
- Root `pnpm dev` starts Django and Next natively and concurrently, both hot-reloading, with a note that `docker compose up` must be running first. On Windows, **verify this rather than assuming** — if turbo's persistent tasks misbehave, say so and use whatever actually works.

**Done when:** `docker compose up -d` then `pnpm dev` gives a hot-reloading Django on :8000 and Next on :3000.

### 0.11 — CI

`.github/workflows/ci.yml`:
- Postgres 17 (pgvector image) and Redis 7 as service containers.
- Jobs: `lint` (ruff, mypy, eslint, prettier), `typecheck` (tsc), `test-api` (pytest plus `check_coverage.py`), `test-web` (vitest), `contracts` (`lint-imports`).
- `makemigrations --check --dry-run` — declare the step now even though there are no models; Phase 1 makes it meaningful.
- Cache the uv and pnpm stores.
- Triggers on push and pull request.

**Done when:** the workflow parses and every step it runs passes locally by the same commands.

### 0.12 — pgvector verification and `docs/deploy-railway.md`

- Confirm `CREATE EXTENSION vector;` succeeds against the dev compose Postgres. Record the exact image tag.
- Create `docs/deploy-railway.md` with a section recording the pgvector answer **for the target host**, not only for dev. Railway's extension availability is a property of its Postgres plugin version — check it, and if it cannot be checked without an account, say so explicitly as an open item with the exact question to answer. Do not write a confident sentence you did not verify.

**Done when:** the extension creates on the dev image, and the doc either states the target-host answer or names it as unresolved.

---

## Acceptance — every box needs pasted evidence

- [ ] `docker compose -f infra/compose.dev.yml up` starts Postgres, Redis and Mailpit **and nothing else**
- [ ] `pnpm dev` runs Django and Next natively, both hot-reloading
- [ ] `pnpm lint`, `pnpm typecheck`, `pnpm test` pass across all workspaces
- [ ] CI runs all three on push, with coverage evaluated per directory rather than globally
- [ ] `scripts/check_coverage.py` fails on a path below its threshold **and** on a glob that matches nothing, naming the path and both figures
- [ ] Adding a file to `keel/domain/` that imports the ORM fails the contract check; the contract is silent while the directory is absent
- [ ] The `keel.core` → `keel.organizations` contract is declared and passes
- [ ] Mailpit catches a test email at `localhost:8025`
- [ ] `CREATE EXTENSION vector` succeeds on the dev image, and the target-host answer is recorded in `docs/deploy-railway.md`
- [ ] `manage.py check --deploy` produces no error under `config.settings.prod` (warnings are fine — list them)
- [ ] `git status` is clean, with nothing untracked that should be ignored

---

## How to work

- **Strict TDD does not apply to scaffolding**, and pretending otherwise wastes the phase. Write the config, then write the test that proves the config does what it claims. Two proofs must be demonstrated by deliberately breaking something and showing the failure output: the import-linter contract, and the coverage gate.
- **Verify, do not assert.** Every acceptance box needs pasted command output. "Should work" is not a result. If something does not work on Windows, report exactly what and what you did instead — that is useful information about the template, not a failure.
- **Do not install a dependency a later phase owns** to make a placeholder look complete.
- **Do not create `keel/domain/`.**
- Commit in coherent chunks with real messages, not one commit at the end.
- If this plan and `keel-prd.md` conflict, the PRD wins and you report the conflict.

## Report back

What passes, what does not, every acceptance box with its evidence, anything you had to decide that this plan did not cover, and anything in the PRD that looked wrong from inside the code.
