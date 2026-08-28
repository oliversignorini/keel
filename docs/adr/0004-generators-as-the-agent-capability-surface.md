# ADR 0004 — Generators, not prompts, are Keel's capability surface

**Status:** Accepted — 2026-08-28
**Decides:** whether `.claude/commands/*.md` remain the mechanism by which a
new vertical slice is created, or become thin wrappers over a shipped CLI.

---

## Context

`.claude/commands/` holds seven Markdown files. They are not code and they
are not registered anywhere: Claude Code globs the directory, maps the
filename to a slash command, and injects the body into the model's turn.
`$ARGUMENTS` interpolates. That is the entire mechanism.

Which means `/new-resource` — a command whose body says "copy the shape of
`apps/api/keel/widgets/` file for file, do not invent a different structure"
— is a deterministic, mechanical act being performed by a nondeterministic
thing. Every invocation re-derives the same nine files from prose, at full
token cost, with a fresh opportunity to get invariant 6's
`organization_scoped` declaration or invariant 7's `@audited` decorator
subtly wrong. The failure is quiet: the slice looks right, and review is
what catches it.

Two further problems follow from the same root:

- **Drift.** The commands describe a file shape that lives in the codebase.
  Nothing checks that the description still matches. When `keel/core/authz.py`
  changes, seven Markdown files silently become wrong.
- **Legibility.** A prompt is legible to the model and to nobody else. A
  human contributor reading `.claude/commands/new-resource.md` learns what
  an agent is told, not what the repository can do.

Keel already ships one real CLI — `scripts/init.ts`, which rewrites the
project name and tenant noun across the whole repo, applies feature toggles,
and deletes itself. Instantiation is a program. Slice creation is a prompt.
There is no principled reason for the split.

## Decision

**Mechanical generation moves into a shipped CLI; the slash commands become
thin wrappers around it.**

The CLI (`packages/cli`, invoked as `pnpm gen <generator>`) emits a
conforming, compiling, tested skeleton. The `.md` command then drives the
agent through the parts that require judgement — the field list, the
business rules, the bespoke permissions. Neither half does the other's job.

Three consequences are load-bearing and are decided here, not left to the
implementation:

1. **The CLI ships.** It is a product feature of the template, not
   authoring scaffolding. `init.ts` renames it along with everything else;
   downstream projects keep it forever. A template whose seven invariants
   are enforceable only by a model reading `CLAUDE.md` is weaker than one
   with a generator that cannot emit a non-conforming slice.

2. **Templates are the source; `widgets/` is a render of them.** The
   reference slice stops being hand-edited. CI regenerates it and asserts
   `git diff --exit-code`, the same idiom already used for
   `openapi.merged.json` and `packages/api-client/src/generated`.
   Improvements land in the template and flow outward.

3. **The generator's output is gated in CI.** A job generates a throwaway
   slice into the disposable CI checkout and runs the real invariant suite
   against it, on every pull request. Without this, the drift merely moves
   from prose into templates.

Templates are real `.py` and `.tsx` files using token substitution
(`__Resource__`, `__resource__`, `__app__`) rather than a template language,
so ruff, mypy, eslint and tsc lint the templates themselves. A `.hbs` file
is unlintable text.

## Why this is an architectural decision and not a convenience

The seven invariants in `CLAUDE.md` are currently enforced in two places:
automated gates that fail _after_ the code is written, and prose that hopes
it is written correctly the first time. This ADR adds a third position — the
moment of creation — and asserts it is the strongest of the three. A slice
that arrives conforming does not need to be argued back into conformance.

It also fixes what the repository _is_ to an agent. Given a vague brief
("we need invoicing, it connects to organisations like this"), an agent's
options today are to read `CLAUDE.md`, read `widgets/`, and hand-write forty
files. After this, its first move is to read a catalogue of what can be
provisioned and provision it. The remaining conversation is about the
feature, not about the file shape.

## Scope boundaries

- `gen resource` **never** regenerates `openapi.merged.json` or the
  TypeScript client. That stays a separate `gen sync-client` subcommand,
  because only one worktree at a time may write those paths (see
  `CLAUDE.md`). `sync-client` takes a lock in the shared `.git`
  directory, turning a convention that existed only in Markdown into
  something the machine enforces.
- The generator is **not dogfooded inside keel**. Every run emits a
  migration, and `WORKTREES.md` rule 2 forbids migrations outside a phase
  that declares one. The CI harness and `widgets/` together are sufficient
  proof it works.
- `new-connection` stays a prompt. Wiring a third-party OAuth provider is
  configuration and judgement with high per-provider variance; there is no
  mechanical core to extract.

## Alternatives considered

**Keep prompt-only generation.** Zero work. Rejected: it preserves all three
failures — nondeterminism, drift, and cost — and forfeits the point below
about legibility.

**Full codegen, delete the commands.** A generator that also writes the
domain logic. Rejected: the judgement half is exactly what a model is good
at and what a template cannot know. Growing the field DSL until it can
express Django's model API is a trap with no natural stopping point.

**A machine-readable catalogue (`gen --json`) alongside `--help`.**
Rejected: the same information expressed twice, and the copy that is read
less often goes stale. `--help` is machine-readable enough.

**A declarative slice spec (`keel apply slices/invoice.yaml`).** Rejected
for now: it is a configuration language that would need versioning,
documentation and migration, and its one real advantage — a durable record
of what was provisioned — is already provided by git plus the CLI invocation
in the commit message. Revisit only if slices ever need re-applying after a
template change.
