# Phase 9 — Release credibility pack

**Source of truth:** `docs/review-2026-08.md` §3, and the "Open-source release polish" and "CI as product" sections of the Notion production-readiness checklist.
**Depends on:** nothing. Start immediately.
**Size:** Small ×4.
**Parallelism:** **four worktrees, concurrently.** Path ownership below is disjoint by construction — check it before you write a file outside your slice.

---

## Why this phase exists

Keel is a good codebase in a repository that would not survive a stranger's
first thirty seconds. There is no licence, so "open source" is legally
meaningless. The README links to a file that does not exist. Nothing tells
an agent working here what the invariants are. CI never runs Django's own
production checks.

None of that is hard. All of it is embarrassing. It is also the only wave
that parallelises perfectly, because none of it touches `apps/`.

---

## Boundary

**In scope:** repository metadata, documentation, CI configuration, agent
instructions.

**Out of scope — for every slice:**

| Thing | Owner |
|---|---|
| Anything under `apps/` | Phases 10–16 |
| `keel-prd.md`, `docs/plans/*`, `docs/adr/*`, `docs/review-*.md` | The orchestrator |
| Fixing anything a new CI gate reports | 9.C reports it; the owning phase fixes it — see 9.C |
| `scripts/init.ts` | Phase 17 |

**No migrations. No changes to `apps/api` or `apps/web` source.** The one
exception is 9.C adding dev-dependencies to `apps/api/pyproject.toml`.

---

## Path ownership

| Slice | Owns |
|---|---|
| 9.A | `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md`, `.github/dependabot.yml` |
| 9.B | `docs/architecture.md`, `docs/auth-flow.md`, `docs/diagrams/`, the "Layout" and "invariants" sections of `README.md` |
| 9.C | `.github/workflows/ci.yml`, `.github/workflows/security.yml`, `apps/api/pyproject.toml` (dev-dependencies only), `.gitleaks.toml` |
| 9.D | `CLAUDE.md`, `.claude/commands/` |

`README.md` is touched by 9.B only. If another slice needs a README change,
put it in the report.

---

## 9.A — Repository metadata

**Licence.** MIT unless there is a reason to prefer otherwise; a template
nobody may legally copy is not a template. Copyright line: `Oliver
Signorini`. Add a licence line to `README.md`'s footer — coordinate with
9.B, or leave it in your report and let 9.B place it.

**`SECURITY.md`.** Supported versions, how to report a vulnerability
privately (GitHub private vulnerability reporting), expected response time.
Do not invent an SLA you will not meet — "best effort, this is a solo
project" is a more credible sentence than "24 hours".

**`CONTRIBUTING.md`.** How to get the dev environment up (link
`docs/dev-setup.md` rather than duplicating it), what CI enforces, and the
invariants a PR must not break. That last part matters most: a contributor
who adds a viewset without `GLOBAL_JUSTIFICATION` should learn it from this
file, not from a red build.

**`CHANGELOG.md`.** Keep a Changelog format. Seed with an `[Unreleased]`
section and one entry per merged phase, derived from `git log`, not from
memory.

**Issue and PR templates.** Bug report, feature request, and a PR template
whose checklist names the invariants — tests for both allow and deny paths,
no new migration, generated client regenerated if the API changed.

**`.github/dependabot.yml`.** Four ecosystems, all present in this repo:
`pip` (`/apps/api`, `uv.lock` — verify Dependabot supports `uv` for this
layout and fall back to `pip` on `pyproject.toml` if not), `npm`
(`/`, pnpm workspace), `github-actions` (`/`), and `docker` (`/infra`).
Weekly, grouped minor+patch, so it does not generate twenty PRs a week.

---

## 9.B — Architecture documentation

**`docs/architecture.md` — the missing file `README.md:68` already links
to.** This is the most valuable single document in the phase.

It must contain **all seven invariants**, since the README promises them
here and describes only four. Derive them from `keel-prd.md` §4
"Architecture Invariants" — read it, do not paraphrase the README. For each:
what it is, why it exists, and **the file that enforces it**, with a path.
An invariant with no enforcement mechanism named is a convention; say so
plainly if you find one.

Then: the request path from browser to database, the app layout and the
per-app file shape, where business logic lives (`services.py` writes,
`selectors.py` reads), and the type-synchronisation pipeline
(Django → drf-spectacular → `merge_openapi.py` → orval → `apps/web`).

**Note the pipeline is about to change.** ADR 0001 replaces DRF with Ninja
in Phase 10. Write the section describing today's reality and add a short
note pointing at the ADR — do not document a future that has not been built.

**`docs/auth-flow.md`.** The request diagram the direction proposal asks
for. Signup, login, session refresh, cross-host cookie behaviour, CSRF
acquisition, and the 401-vs-403 distinction. `docs/auth-client-contract.md`
has the mechanics; this is the picture. Mermaid sequence diagrams, in the
markdown, not binary images.

**`docs/diagrams/`.** System diagram — two Next.js hosts, Django, Postgres,
Redis, Celery, Stripe, S3-compatible storage. Mermaid. Every diagram must
render on GitHub; check it rather than assuming.

**README.** Fix the `docs/architecture.md` link once it exists, add links to
the new documents, and update the status line — Phase 9 is no longer "the
init script" (that is Phase 17 now).

---

## 9.C — CI security and production gates

Add gates. **Do not fix what they find** — that is a different phase's work
and a different worktree's files.

Every gate below must be added in a state where **CI is green on merge**. If
a gate fails on the current codebase, you have two honest options: fix it if
it is genuinely a one-line configuration issue, or land it non-blocking
(`continue-on-error: true`) with a `TODO` naming the phase that owns the
fix, and put the full finding in your report. Landing a red gate is not an
option; neither is quietly narrowing it until it passes.

**`manage.py check --deploy`.** Under `config.settings.prod`, in the
`test-api` job. This will need a set of environment variables to even
import; supply them inline in the workflow as obvious placeholders. Errors
fail the build, warnings are printed. Expect findings — `SECRET_KEY` has an
insecure default (`base.py:44`) and that is Phase 16's to fix.

**Bandit.** `apps/api`, in the `lint` job. Configure exclusions in
`pyproject.toml`, with a comment per exclusion.

**`pip-audit`** over the `uv` lockfile, and **`pnpm audit`** over the
workspace. Both in a new `security.yml`, on push and on a weekly schedule —
a dependency advisory published on Tuesday should not wait for someone to
push.

**Wire `e2e/auth-flows.spec.ts` into CI.** It is written and has never
run — PRD v1.3 lists it as outstanding. It needs the live Django API and
Mailpit as service containers, which is the reason it was deferred and is
ordinary workflow plumbing, not application work. Add them to the
`e2e-accessibility` job (rename it, since it is no longer only accessibility)
and run both specs. If the suite fails for a real reason, land it
non-blocking with a TODO and report the failure — the same rule as every
other gate here.

**Secret scanning.** `gitleaks` in `security.yml`, over full history
(`fetch-depth: 0`). This repo has already had `.env.bak` committed and
removed (`7fd5a99`); scan history, not just the tip. If history is dirty,
**do not rewrite it** — report it.

---

## 9.D — `CLAUDE.md` and slash commands

The agent-facing half of PRD §8 Phase 9. Phase 17 builds `init`; this slice
builds what `init` will later template.

**`CLAUDE.md`,** at the repo root. What an agent must know before writing a
line here: the per-app file shape, that authorization lives in exactly one
file, that tenant scoping is declared and cross-tenant access answers 404,
that every mutating service is `@audited` or `@not_audited`, that the schema
is one baseline migration, that `packages/api-client/src/generated` is never
hand-edited, and the commands that verify each of those. Link
`docs/architecture.md` rather than restating it — assume 9.B lands.

Add the "use Django first" defaults the Notion checklist calls for: auth,
pagination, caching, email, files, management commands, checks and storage
abstractions are Django's, and an agent that reinvents one is making the
template worse.

Keep it short enough to be read every session. Under 200 lines.

**`.claude/commands/`.** The eight commands from PRD §8 Phase 9:
`/new-resource`, `/new-readonly-resource`, `/new-job`, `/new-permission`,
`/new-connection`, `/check-invariants`, `/sync-client`, `/new-email`.

Each is a markdown prompt file. Each must generate code that already
satisfies the invariants — a `/new-resource` that produces a viewset without
`test_factory` is worse than nothing, because it teaches the failure.

`/check-invariants` is the one to build first and the one to get right: it
should run the meta-tests, the permission lint, `lint-imports`, the coverage
gate, and the client-drift check, and report which invariant each covers.

**Write these against today's DRF structure.** Phase 10 will rewrite them;
that is expected and is cheaper than not having them.

---

## Acceptance — evidence required

**9.A**
- [ ] `LICENSE` present; the licence is named in `README.md`
- [ ] `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md` present
- [ ] `CONTRIBUTING.md` names the invariants a PR must not break
- [ ] Issue templates and a PR template render correctly in the GitHub UI
- [ ] `dependabot.yml` validates and covers pip, npm, github-actions, docker

**9.B**
- [ ] `docs/architecture.md` exists and `README.md:68` resolves
- [ ] All **seven** invariants documented, each naming its enforcing file by path
- [ ] `docs/auth-flow.md` covers signup, login, session, CSRF, 401 vs 403
- [ ] Every Mermaid diagram renders on GitHub — verified, not assumed
- [ ] README status line reflects the Phase 9–18 sequence

**9.C**
- [ ] `check --deploy` runs in CI under `config.settings.prod`
- [ ] Bandit, `pip-audit`, `pnpm audit`, `gitleaks` all run
- [ ] `e2e/auth-flows.spec.ts` runs in CI against a live API and Mailpit
- [ ] `gitleaks` scans full history, not just the tip
- [ ] **CI is green on merge**, with any non-blocking gate carrying a TODO naming its owning phase
- [ ] Every finding is in the report, with the phase that should fix it

**9.D**
- [ ] `CLAUDE.md` under 200 lines, covering all seven invariants and their verification commands
- [ ] Eight command files exist
- [ ] `/new-resource` output passes `/check-invariants` — demonstrated end to end
- [ ] `/check-invariants` runs every gate and maps each to an invariant

---

## How to work

One worktree per slice, branched off `master`. Do not edit outside your
slice's path list. If you need something from another slice, assume it
lands and note the assumption.

Commit per coherent unit, not per file.

## Report back

- What you added, and the paths
- For 9.C: every finding, with the phase that owns the fix, and whether the
  gate landed blocking or non-blocking
- Anything you found that contradicts `docs/review-2026-08.md` — that
  document was written from a single pass and is fallible
- Anything you were about to fix outside your boundary and deliberately did
  not
