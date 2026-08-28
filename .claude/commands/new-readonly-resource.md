Generate a read-only vertical slice for the resource named in
`$ARGUMENTS` — `pnpm gen readonly-resource` instead of `pnpm gen
resource`, minus every write path (ADR 0004, `docs/plans/phase-19.md`).
Use this for reference data, computed views, or anything the API only
ever lists and retrieves.

**Ask first** whether this resource is org-scoped or global if it isn't
obvious. A resource that is legitimately identical across every tenant
(enrichment data, shared taxonomies) is a `GlobalViewSet` with a
`GLOBAL_JUSTIFICATION` — the generator does not emit that path; get the
justification from the caller and wire it by hand rather than inventing
one, since invariant 6 requires it to be a real paragraph, not
boilerplate.

## 1. Run the generator

```
pnpm gen readonly-resource __Resource__ --fields "period:str(32),total:decimal"
```

Same `--fields` DSL as `/new-resource`. This emits `models.py`,
`migrations/0001_initial.py`, `selectors.py`, list/retrieve-only
`schemas.py`/`views.py`, `admin.py`, a factory, and tests — no
`services.py`, no write schemas, one `<resource>.view` permission code
instead of the CRUD four — and runs the same DB-free gates `/new-resource`
does.

## 2. Do the judgement work

- If something writes this data out-of-band (a sync task, an import job),
  add `services.py` by hand with `@audited`/`@not_audited` on the writer —
  the generator has no flag for "read-only API, but not read-only data".
  Run `/new-job` if the write is task-driven.
- If this is genuinely global (not org-scoped), swap the generated
  `OrgScopedViewSet` base for `GlobalViewSet` and write the
  `GLOBAL_JUSTIFICATION` — see PRD §4 invariant 7, "Where a global table
  has a tenant-scoped companion" for the shape of the accompanying test
  that proves no tenant-private relationship leaks through its id space.

## 3. Sync the client

`pnpm gen sync-client` in whichever worktree owns the generated client
this wave.

## 4. Finish

`/check-invariants`, then `pnpm gen e2e __Resource__` once the feature is
actually finished (list/retrieve path only — there's no create/edit/
delete flow to exercise on a read-only resource, so treat its happy path
as list-then-retrieve).
