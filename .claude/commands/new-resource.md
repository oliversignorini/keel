Generate a full CRUD vertical slice for the resource named in `$ARGUMENTS`
(a singular PascalCase model name, e.g. `Invoice`), then do the judgement
work the generator deliberately leaves undone (ADR 0004).

**Ask first** if the app name (the CLI derives it as the lowercase plural
of the resource, e.g. `invoices`) isn't right for this resource, or if you
don't have a field list yet — get `--fields` before generating, since a
re-run over an existing app needs `--force` and overwrites hand-written
domain logic.

## 1. Run the generator

```
pnpm gen resource Invoice --fields "name:str,description:text?,status:choice(draft,live)"
```

Field DSL: `str`, `str(N)`, `text`, `int`, `decimal`, `bool`, `date`,
`datetime`, `choice(a,b,c)`, `fk(<app>.<Model>)`. A trailing `?` makes a
field optional. Run `pnpm gen --help` for the full reference. Pass
`--permissions manage` instead of the default `crud` if the resource wants
the coarser `<resources>.view`/`.manage` pair rather than four separate
CRUD codes.

This emits the model, migration, selectors, services, schemas, views,
tasks, admin, factory and tests; wires `INSTALLED_APPS` and the org-scoped
router; emits the four CRUD permission codes; and runs the DB-free gates
(`makemigrations --check`, `lint-imports`, `check_permission_lint.py`),
failing loudly if any of them don't pass. The command's own output tells
you exactly which files were written and which anchors were spliced —
trust that list over re-reading the tree.

Pass `--ui` if this resource needs frontend pages: a list, create and
detail route assembled from `@keel/ui`'s existing primitives, plus a
thin `apps/web/lib/<resources>/api.ts` wrapper. Not supported yet on
`readonly-resource`.

## 2. Do the judgement work the generator left as insertion points

- Fill in `services.py`'s business rules — the generator writes create/
  update/delete with the transaction boundary and `@audited` decorators
  already in place; what's missing is anything domain-specific (extra
  validation, side effects beyond the Tier-1 notify hook).
- Add any bespoke permission code (e.g. `invoice.export`) with
  `pnpm gen permission <code>` — the generator only emits the four CRUD
  codes.
- If this resource dispatches async work beyond the generated Tier-1
  notify task, or needs a Tier-2 job, run `/new-job`.
- Add fields' `Meta`, indexes, and cross-field validation the DSL doesn't
  express — the generator leaves a marked insertion point in `models.py`
  for exactly this.

## 3. Sync the client

`pnpm gen sync-client` in whichever worktree owns the generated client
lock (`docs/plans/WORKTREES.md` rule 3) — the resource generator
never regenerates it itself.

## 4. Finish

`/check-invariants` — fix anything it reports before considering this
done. Once the feature (backend and, if generated with `--ui`,
frontend) is actually finished, `pnpm gen e2e Invoice` is the ship
gate: it writes a Playwright spec for the happy CRUD path and runs the
full `/check-invariants` suite including `pytest`. An output that fails
either is not a finished `/new-resource` run.
