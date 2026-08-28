Regenerate the TypeScript API client from the current Django + allauth
OpenAPI specs. Run this any time a view, schema, or route changed.

## Run the generator

```
pnpm gen sync-client
```

This is the _only_ command allowed to touch `openapi.merged.json` or
`packages/api-client/src/generated` (see CLAUDE.md — only one worktree at
a time may write those paths) —
it takes a lock in the shared `.git` directory (worktrees share it) and
refuses to run if another worktree already holds it, rather than relying
on remembering the rule.
If it refuses, wait for that run to finish; pass `--force` only if you're
certain a crashed run left the lock behind.

It runs, in order: merge the Ninja and allauth specs into
`openapi.merged.json`, run orval over the merged spec, typecheck the
generated client, typecheck `apps/web` against the new types. It then
reports which of `openapi.merged.json` / `packages/api-client/src/generated`
changed — **never hand-edit anything under `generated/`**; if the output
looks wrong, the fix is in the Django view/schema or in
`orval.config.ts`, not in the generated file.

## Finish

If the client changed, commit it — CI's `api-client-generation` and
`contracts` jobs both fail on drift here, so commit alongside the change
that caused it. If `apps/web` consumes the changed endpoint, update its
call sites (the typecheck step above will have already told you what
broke). Report which files changed (new endpoints, changed shapes, or
none) — don't just say "regenerated."
