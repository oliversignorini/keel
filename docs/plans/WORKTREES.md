# Kicking off the worktrees

Every plan file is written to be handed to an implementation agent as-is.
The prompt is the same shape each time:

```
Read docs/plans/phase-N.md and implement slice X. It is the specification —
follow its Boundary section exactly and do not edit files outside your
slice's path list. Read docs/review-2026-08.md for context on the state of
the repo. Report back in the shape the plan's "Report back" section asks for.
```

`git worktree add ../keel-p9a -b p9a-repo-meta master`, one per slice.

## What can run at the same time

| Wave | Worktrees | Branch suggestion |
|---|---|---|
| **1 — now** | Phase 9.A repo metadata | `p9a-repo-meta` |
| | Phase 9.B architecture docs | `p9b-arch-docs` |
| | Phase 9.C CI security gates | `p9c-ci-gates` |
| | Phase 9.D `CLAUDE.md` + commands | `p9d-claude-md` |
| | Phase 10 Ninja migration (long-running) | `p10-ninja` |
| | Phase 12 Railway deploy | `p12-railway` |
| **2 — after 10 merges** | Phase 11 auth BFF | `p11-auth-bff` |
| | Phase 13 document storage | `p13-storage` |
| | Phase 14 billing polish | `p14-billing` |
| | Phase 15 jobs and audit | `p15-jobs-audit` |
| **3 — after 13/14/15** | Phase 16.A query hygiene | `p16a-queries` |
| | Phase 16.B settings and secrets | `p16b-settings` |
| | Phase 16.C rendering and boundaries | `p16c-boundaries` |
| **4 — serial, last** | Phase 17 `init`, then Phase 18 release | `p17-init`, `p18-release` |

Six concurrent worktrees in wave 1. Phase 10 will outlive the other five —
that is expected; it is five stages and it blocks wave 2.

## The three rules that keep them from colliding

1. **`keel-prd.md`, `docs/plans/*`, `docs/adr/*` and `docs/review-*.md`
   belong to the orchestrator.** A worktree that wants one changed says so
   in its report.
2. **No migrations** outside a phase that declares one. Phase 13 declares a
   model migration; Phase 16.A declares an index-only migration. Nothing
   else does.
3. **One worktree at a time** may regenerate `openapi.merged.json` or
   `packages/api-client/src/generated`. In wave 1 that is Phase 10's, and
   nobody else's.

## Merge order within wave 1

9.A, 9.C and 9.D are independent and can merge in any order. 9.B touches
`README.md` and should merge after 9.A, which adds the licence line it
references. Phase 10 merges last — it is the one that will need rebasing.
