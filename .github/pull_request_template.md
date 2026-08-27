## What this does

<!-- One or two sentences. Link an issue if there is one. -->

## Checklist

- [ ] Tests cover both the **allow path and the deny path** — not just the
      happy path (`keel-prd.md` §4 invariant 7; see `CONTRIBUTING.md`)
- [ ] No new migration, or the migration is expected by the phase/plan this
      PR implements — the schema is one baseline migration otherwise
- [ ] If a viewset was added or changed: it declares `required_permissions`
      and either `organization_scoped = True` + `test_factory`, or a
      `GLOBAL_JUSTIFICATION`
- [ ] If a mutating service was added or changed: it is `@audited(action)`
      or `@not_audited(reason=...)`
- [ ] If the API surface changed: `packages/api-client/src/generated` was
      regenerated and the diff is committed (`pnpm --filter @keel/api-client generate`)
- [ ] `pnpm lint` and `pnpm typecheck` pass locally
- [ ] CI is green

## Anything reviewers should know

<!-- Deliberate scope cuts, follow-up work, things you're unsure about. -->
