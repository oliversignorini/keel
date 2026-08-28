Turn a brain dump in `$ARGUMENTS` — "we need invoicing, it connects to
organisations like this, finance can export it" — into a provisioning
plan: which generators to run, in what order, and what remains manual
judgement. **Do not run anything yet.** The user approves the plan before
a single generator runs (ADR 0004).

Consult `CLAUDE.md`'s generator catalogue first — that table plus
`pnpm gen --help` is the whole discovery mechanism for what this
repository can provision. Do not hand-write a slice this table already
covers.

## 1. Decompose the brief

Read `$ARGUMENTS` for:

- **Resources** — nouns that need their own CRUD or read-only API and
  (if this project has `--ui`) pages. Each becomes a `gen resource` or
  `gen readonly-resource` call, with a `--fields` guess to confirm with
  the user, not invent silently.
- **Relations** — an "X connects to Y" sentence is a `fk(<app>.<Model>)`
  field on X, not a separate generator step.
- **Permissions** — anything narrower than a resource's default CRUD
  codes ("finance can export it") is a `gen permission` call.
- **Async work** — anything that happens in the background, on a
  schedule, or after an external event is a `gen job` call. Decide Tier 1
  vs Tier 2 per `/new-job`'s rule; **ask** if the brief doesn't make it
  obvious.
- **Third-party integrations** — OAuth wiring is `/new-connection`, not a
  generator; note it as a manual step.
- **Anything with no generator** — say so explicitly rather than folding
  it into the nearest generator call. A brief that needs a report, a
  dashboard widget, or a cross-resource computation names work no
  generator covers; call it out as manual, not `--fields` on the nearest
  resource.

## 2. Order the plan

Dependencies compound in one direction: permissions a resource's routes
need (beyond the default CRUD four) come from `gen permission` calls
that either precede the resource or are cleaned up right after it; a
resource an `fk` field targets must exist (or already exist in the
codebase) before the resource that references it; `gen sync-client` comes
after every backend generator that changed a route, and only once per
worktree holding the client-generation lock (`docs/plans/WORKTREES.md`
rule 3) — don't plan two worktrees regenerating it in the same wave.
`gen e2e` is last, per resource, once its slice (backend, and frontend if
`--ui`) is actually finished.

## 3. Output

**A single-slice feature** (one resource, maybe one permission or job
alongside it): propose the plan directly in chat as a short ordered list
of commands, e.g.:

```
1. pnpm gen resource Invoice --fields "number:str(32),amount:decimal,due_on:date,customer:fk(accounts.Customer)?"
2. pnpm gen permission invoices.export
3. Manual: implement services.py business rules, wire the export permission onto the export route
4. pnpm gen sync-client
5. pnpm gen e2e Invoice   (once finished)
```

**A feature spanning several generators or worktrees** (e.g. a resource,
an export permission, a rollup job, and a settings page): write
`docs/plans/<feature>.md` instead — the artifact a second agent picks up
without re-deriving the plan from the original brief. Use an existing
plan under `docs/plans/` as the shape to copy: what this is, scope
boundary (paths in/out), the ordered steps above broken into waves if
more than one worktree is involved, and an acceptance checklist. A plan
file for `gen resource Invoice --ui` alone is ceremony; a plan file for
invoicing plus an export permission plus a rollup job plus a settings
page is what keeps a multi-worktree effort coherent.

## Finish

Present the plan (in chat or as the written file) and stop. Wait for the
user to approve, adjust, or reject it before running any generator.
