# Phase 19 — Generators: the CLI capability surface

**Source of truth:** `docs/adr/0004-generators-as-the-agent-capability-surface.md`.
**Depends on:** UX slices A–D merged (done — `87a82bc`). `uxc-widgets` defines
the frontend template, so nothing here may start before it lands.
**Size:** Medium. Three slices, two waves.

---

## What this is

`.claude/commands/*.md` currently ask a model to hand-write a nine-file
vertical slice from prose. This phase moves the mechanical half into a
shipped CLI — `pnpm gen <generator>` — and reduces each command to a wrapper
that runs it and then drives the judgement half. ADR 0004 carries the
argument; this file is the specification.

The end state:

- `packages/cli`, a workspace package, invoked as `pnpm gen …`, renamed
  along with everything else by `scripts/init.ts` and shipped to every
  instantiated project.
- Templates are real `.py`/`.tsx` files with `__Resource__`-style token
  substitution, so the linters lint the templates.
- `apps/api/keel/widgets/` and `apps/web/app/(app)/app/[org]/widgets/` are
  **renders of** those templates, held there by a `git diff --exit-code`
  regen check.
- CI generates a throwaway slice on every PR and runs the real invariant
  gates against it.

## Boundary — the whole phase

**In scope:** `packages/cli/**`, `templates/**` (new, repo root),
`.claude/commands/**`, `.github/workflows/**`, `scripts/init.ts` (rename +
retention of the CLI), `CLAUDE.md` (the generator catalogue), and whatever
regenerating `widgets/` from templates produces.

**Out of scope:**

- **Migrations.** `WORKTREES.md` rule 2 stands. The generator is never run
  inside keel; it is exercised by the CI harness in the disposable checkout
  and by `widgets/` being a render. No slice in this phase adds a migration
  to this repository.
- **`openapi.merged.json` and `packages/api-client/src/generated`.** Rule 3
  stands. No slice here regenerates them; `gen sync-client` is built, not
  run.
- **`new-connection`.** Stays a prompt. Third-party OAuth wiring has no
  mechanical core worth extracting.
- **Domain features.** Nothing in `apps/api/keel/*` other than `widgets/`
  changing because it is now generated.

## Waves

| Wave | Slice | Branch |
| --- | --- | --- |
| **1 — first, alone** | 19.A CLI foundation, `resource`, `readonly-resource`, `permission`, `sync-client`, CI harness | `p19a-gen-core` |
| **2 — after 19.A merges** | 19.B `job`, `gen e2e`, `/plan-feature`, command rewrites | `p19b-gen-jobs` |
| | 19.C `--ui` frontend templates, `email` | `p19c-gen-ui` |

19.A is alone in wave 1 deliberately: it establishes the template
convention, the token-substitution rules and the marker-comment syntax. Two
worktrees inventing those independently is the one collision this phase can
produce that nothing catches.

**Deviation from the original split, recorded:** the `permission` generator
was scoped as wave-2 work, but `gen resource` shells out to it for the four
CRUD codes (see 19.A below), so it is a hard dependency and moves into 19.A.
`email` moves to 19.C to keep the waves balanced.

---

## Slice 19.A — CLI foundation

**Paths:** `packages/cli/**`, `templates/resource/**`,
`templates/readonly-resource/**`, `templates/permission/**`,
`apps/api/keel/widgets/**` (as regenerated output), `.github/workflows/**`,
`scripts/init.ts`, `package.json`, `pnpm-workspace.yaml`, `turbo.json`.

### The package

`packages/cli`, TypeScript, in turbo, typechecked and unit-tested like any
other workspace package — not a loose script. Root `package.json` exposes
`"gen": "node packages/cli/dist/index.js"` so the invocation is
`pnpm gen resource Invoice`, stable across every instantiated project and
therefore safe to hard-code into `CLAUDE.md` and the slash commands.

`scripts/init.ts` renames the binary and its help text along with the
project name. A leftover `keel` in an instantiated Acme repo is exactly the
template smell the rest of `init.ts` exists to remove. `init.ts` must **not**
delete `packages/cli` — unlike the reference slice, this ships.

### Templates

Real `.py` files under `templates/resource/`, mirroring the seven-file shape
from `CLAUDE.md`. Substitution tokens only:

```
__Resource__   PascalCase singular    Invoice
__resource__   snake_case singular    invoice
__resources__  snake_case plural      invoices
__Resources__  PascalCase plural      Invoices
__app__        app label              invoices
```

Conditional regions use sparse marker comments — `# keel:if fk` …
`# keel:endif` — and nothing more. If a template ever needs loops or
expressions, that is the signal the template is doing too much, not a signal
to adopt a template engine.

The point of this format is that every template file is valid Python and is
linted by the repo's existing ruff/mypy configuration. Do not introduce a
`.hbs`, `.eta` or `.j2` file anywhere in this phase.

### `gen resource <Name>`

Flags: `--fields`, `--ui` / `--no-ui`, `--dry-run`, `--force`, `--no-verify`.

`--fields` is deliberately minimal. Supported types: `str`, `text`, `int`,
`decimal`, `bool`, `date`, `datetime`, `choice(a,b,c)`, and
`fk(<app>.<Model>)`. `fk` earns its place because a relation changes four
files, not one. Everything past this — constraints, indexes, `Meta`,
nullability — is judgement: the templates leave a marked insertion point and
the slash command tells the agent to fill it. Do not grow the DSL toward
Django's field API.

Emits, per `CLAUDE.md`'s per-app file shape: `models.py`,
`migrations/0001_initial.py`, `selectors.py`, `services.py`,
`serializers.py`, `views.py`, `urls.py`, `tasks.py`, `admin.py`, plus
`tests/factories.py` and tests (below).

**Files it does not own**, spliced at anchor comments
(`# keel:generated-apps — do not remove` and equivalents): `INSTALLED_APPS`,
the org-scoped router registration, and — in 19.C — web navigation. Anchors
are ugly and survive user edits; full AST rewriting is disproportionate for
four call sites.

**Permissions.** `gen resource` shells out to `gen permission` for the four
CRUD codes (`invoice.view`, `.create`, `.update`, `.delete`), because
generated `views.py` declares `_ACTION_PERMISSIONS` referencing codes that
must exist or the app will not import. Invariant 2 requires the *rules* to
live in one file; it does not require that file to be hand-typed. Bespoke
codes such as `invoice.export` stay manual and are the slash command's job.

**Tests emitted:** factory, full CRUD API tests, a tenant-isolation test
asserting cross-org access returns 404, and an assertion that every mutating
service carries `@audited` or `@not_audited`. This is not optional garnish —
the CI harness below runs the real invariant gates against generated output,
and those gates expect these tests to exist.

**Verification.** After writing, run the DB-free gates and exit non-zero on
failure: `makemigrations --check --dry-run`, `uv run lint-imports`,
`scripts/check_permission_lint.py`. Nothing that needs Postgres — the
generator must work in a worktree where `docker compose up` has never been
run. The meta-router test needs a database and belongs to CI.

**Output contract.** On success, print every file written and every anchor
spliced, as an explicit list. This is the single highest-value behaviour in
the phase: it means the calling agent never re-reads the tree to discover
what happened, and knows exactly which files are its to edit next.

`--dry-run` prints that plan and exits 0 without writing. Re-running against
an existing app directory is an error unless `--force`.

### `gen readonly-resource <Name>`

Same, minus the write paths: no mutating services, no write serializers,
list and retrieve only. Shares the template directory structure.

### `gen sync-client`

A port of `.claude/commands/sync-client.md`'s five steps to code. It is the
**only** generator that touches `openapi.merged.json` or
`packages/api-client/src/generated`, and it takes a lock file in the shared
`.git` directory (worktrees share it) and refuses to run if another worktree
holds it. `WORKTREES.md` rule 3 becomes machine-enforced rather than
remembered.

`gen resource` never regenerates the client; it prints an instruction to run
`pnpm gen sync-client` in whichever worktree owns the client this wave.

### `widgets/` becomes a render

Regenerate `apps/api/keel/widgets/` from the templates and commit the
result. From this point the reference slice is not hand-edited: improvements
land in the template. A CI step regenerates it and asserts
`git diff --exit-code`, the same idiom the repo already uses for the merged
OpenAPI spec and the generated client.

Expect this step to surface small inconsistencies in the current `widgets/`.
Each one is either a template improvement or a deliberate exception — record
which, do not paper over it by special-casing the diff.

### CI harness

A new job, running on **every** pull request, not path-filtered:

1. Generate a throwaway slice into the CI checkout — it is disposable, no
   temp-directory machinery needed, and generating in place exercises the
   real anchor splices into `INSTALLED_APPS` and the router.
2. Run the full invariant suite against it: the `/check-invariants` gate set
   plus `pytest`.
3. Commit nothing.

Path-filtering this job is wrong: a change to `keel/core/authz.py` can break
every future generated slice without touching a template. This job is what
replaces the human review that currently catches non-conforming slices.

### Acceptance — evidence required

- [ ] `pnpm gen resource Gadget --fields "..."` in a clean worktree with no
      running database produces a slice that passes all three DB-free gates
- [ ] `--dry-run` prints the file plan and writes nothing
- [ ] Re-running without `--force` exits non-zero and writes nothing
- [ ] Success output lists every file written and every anchor spliced
- [ ] `gen resource` emits the four CRUD permission codes via `gen permission`
- [ ] `apps/api/keel/widgets/` regenerates byte-identical; CI asserts it
- [ ] The CI harness fails when a template is deliberately broken (prove it)
- [ ] `gen sync-client` refuses while another worktree holds the `.git` lock
- [ ] No `.hbs`/`.eta`/`.j2` file exists; ruff and mypy cover `templates/**`
- [ ] No migration added to this repository by this slice
- [ ] `scripts/init.ts` renames the CLI and does not delete it

### Report back

The inconsistencies regenerating `widgets/` surfaced, and for each: template
improvement or deliberate exception. Also, anything the anchor-splice
approach could not express cleanly.

---

## Slice 19.B — `job`, ship gate, and the command rewrites

**Depends on:** 19.A merged.
**Paths:** `packages/cli/**` (job and e2e generators only), `templates/job/**`,
`.claude/commands/**`, `CLAUDE.md`.

### `gen job <Name>`

Ports `.claude/commands/new-job.md`'s mechanical half. Follows invariant 5:
Tier 1 through the `keel/core/tasks.py` shim, Tier 2 as `keel/jobs/` does.
Same output contract, same DB-free verification, same `--dry-run`/`--force`.

### `gen e2e <Resource>` — the ship gate

Not a scaffolder. It writes a Playwright spec for the happy CRUD path
against the generated UI **and** runs the full `/check-invariants` suite
including `pytest`. It is the one command that answers "is this slice
actually done", run when the feature is finished.

Deliberately not part of `--ui`: a `test.skip`'d spec that ships is a test
that never runs.

### Command rewrites

Each of `new-resource`, `new-readonly-resource`, `new-job`,
`new-permission` and `sync-client` becomes: run the CLI, then do the
judgement work. Same slash names — the muscle memory is worth keeping, and
the `.md` remains the right home for the non-mechanical instructions.
Because the command now *invokes* the CLI rather than describing what it
would do, the two cannot disagree.

`new-connection` is not rewritten.

### `/plan-feature`

A new command. Takes a brain dump — "we need invoicing, it connects to
organisations like this, finance can export it" — and produces a
provisioning plan: which generators, in what order, what remains manual. The
user approves before anything runs.

Output shape: proposed in chat for a single-slice feature; written to
`docs/plans/<feature>.md` when it spans several generators or worktrees,
because that is the artifact a second agent picks up. A plan file for
`gen resource Invoice --ui` is ceremony; a plan file for invoicing plus an
export permission plus a rollup job plus a settings page is what keeps it
coherent.

### `CLAUDE.md` catalogue

A short table: what can be provisioned, and the command that provisions it.
Plus the rule that an agent consults it before hand-writing a slice. This
plus `gen --help` is the whole discovery mechanism — do not add a
machine-readable catalogue alongside it (ADR 0004, alternatives).

### Acceptance — evidence required

- [ ] `pnpm gen job …` passes the DB-free gates in a cold worktree
- [ ] `gen e2e Widget` writes a runnable spec and runs the full gate suite
- [ ] All five rewritten commands invoke the CLI and describe only judgement work
- [ ] `new-connection` unchanged
- [ ] `/plan-feature` produces a plan for a multi-slice brief without writing code
- [ ] `CLAUDE.md` catalogue present; no second machine-readable copy of it

### Report back

Which parts of the rewritten commands turned out to still be prose that
should have been code.

---

## Slice 19.C — `--ui` and `email`

**Depends on:** 19.A merged. Parallel with 19.B.
**Paths:** `templates/ui/**`, `templates/email/**`, `packages/cli/**` (ui and
email generators only), `apps/web/app/(app)/app/[org]/widgets/**` (as
regenerated output).

### `--ui`

`uxc-widgets` merged, so `apps/web/app/(app)/app/[org]/widgets/` **is** the
template — extract it, do not design it. `packages/ui` already ships
`data-table.tsx`, `resource-form.tsx`, `form-field.tsx`, `empty-state.tsx`
and `page-header.tsx`; the generated page is assembly of those primitives
plus the orval-generated hooks, not new design. If it needs a new primitive,
that is a signal the primitive belongs in `packages/ui`, not in a template.

Same treatment as the backend reference slice: the widgets pages become a
render of the templates, held by a `git diff --exit-code` check.

`--no-ui` is a first-class path, not an afterthought. Plenty of resources are
internal and have no interface.

Web navigation registration uses the same anchor-comment approach as
`INSTALLED_APPS`.

### `gen email <Name>`

Ports `.claude/commands/new-email.md`'s mechanical half against
`packages/emails` and `keel/notifications/`.

### Acceptance — evidence required

- [ ] `gen resource Gadget --ui` produces a page that typechecks and lints
- [ ] `--no-ui` produces no `apps/web` changes at all
- [ ] The widgets pages regenerate byte-identical; CI asserts it
- [ ] No new UI primitive introduced in a template rather than `packages/ui`
- [ ] Nothing in this slice regenerates the API client

### Report back

Whether the generated page is genuinely assembly of existing primitives, or
whether `--ui` is quietly becoming a second design system.
