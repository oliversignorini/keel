# Phase 17 — Template mechanics (`init`)

**Source of truth:** `keel-prd.md` §8 "Phase 9 — Template mechanics" — unchanged in content, renumbered to 17 (see `docs/review-2026-08.md` §5).
**Depends on:** Phases 9–16, all merged. This is last for a reason.
**Size:** Large.
**Parallelism:** none. `init` rewrites every file in the repo.

---

## Why this moved to the end

`init` rewrites project names, the tenant noun, routes, permission codes,
components and copy across the whole repository, and deletes optional
slices. Every phase before it changes the thing being rewritten. Running it
earlier means writing it twice — the Ninja migration alone would invalidate
every API-shaped rewrite rule.

## Boundary

**In scope:** `scripts/init.ts`, the template CI job, `CLAUDE.md` and
`.claude/commands/` updates that reflect the final structure, template
README.

**Out of scope:** application behaviour. If `init` reveals a problem in
`apps/`, report it — do not fix it here. A change to application code inside
this phase is indistinguishable from an `init` bug.

## Work

Build `scripts/init.ts` to the PRD's specification. Prompt for project name,
app and API domains, tenant noun, whether to keep the marketing site,
billing shape, demo-slice handling, and the pure domain layer.

The four hard parts, in order of how badly they fail when done carelessly:

1. **Tenant noun rewrite.** "organisation" appears in models, URLs,
   permission codes, route segments, component names, copy, tests and
   migrations. It must rewrite consistently across all of them, including
   plurals, possessives and casing variants (`organization`, `Organization`,
   `organizations`, `org`, `ORG_`). A partial rewrite produces a project
   that imports fine and fails at runtime.
2. **Marketing route deletion** without orphaning a dependency, a route, a
   test or a sitemap entry. `docs/marketing-removal.md` already maps this —
   read it.
3. **Demo slice modes.** Delete, or keep as reference. Both must leave a
   project whose tests pass.
4. **No stale references.** `grep -ri keel` over a generated project must
   return nothing but incidental prose.

Then the docs `init` generates or rewrites: `CLAUDE.md`, architecture docs,
deployment docs, slash commands, template README.

**Template CI**, per the Notion checklist: run `init` against at least one
fixture project, assert no stale references, assert the tenant noun rewrite,
exercise both demo-slice modes, and **run the generated project's full test
suite**. That last one is the only acceptance criterion that actually
matters; the others are ways of finding out why it failed.

## Acceptance — evidence required

- [ ] A fresh instantiation runs, and its dev environment starts
- [ ] `grep -ri keel` over the generated project returns nothing meaningful
- [ ] Tenant noun rewritten completely — verified by generating with a noun that is *not* a synonym of organisation (`team`, `tenant`, `practice`), which catches rules that only work by coincidence
- [ ] Marketing-site removal leaves no orphaned route, import, test or sitemap entry
- [ ] Both demo-slice modes produce a passing project
- [ ] The generated project passes its **full** test suite, including every invariant meta-test
- [ ] The deployment guide works from a clean account for a generated project, not just for Keel
- [ ] Template CI runs all of the above on every push

## Report back

What `init` cannot do and why; every place the codebase resisted being
templated — those are design smells worth naming even if they stay.
