# Phase 15 — Background jobs and audit foundations

**Source of truth:** Notion "Keel Phase 15", `keel-prd.md` §8 Phase 5.5 and Phase 8, `docs/plans/phase-8.md`.
**Depends on:** Phase 10 merged.
**Size:** Small–Medium.
**Parallel with:** Phases 13 and 14.

---

## Read this first — most of this task is already done

The Notion checklist reads as greenfield. It is not:

- `keel/jobs/` has a registry, runner, idempotency, concurrency control,
  pub/sub, SSE live status, and a demo job.
- `keel/audit/` has the model, a recorder, selectors, a read surface, and a
  settings tab.
- `@audited(action)` / `@not_audited(reason=…)` exist **and are enforced** —
  a meta-test walks every `services.py` and fails on any mutating public
  callable decorated with neither, printing every exemption reason in CI.
- Impersonation is recorded, and every audit row carries the impersonator.

"Standardise job status model", "add audit/event trail pattern" and "add
tests for job status and audit creation" are all satisfied. **Do not rebuild
any of it.** Verify, then close the two gaps that are real.

## Boundary

**In scope:** `keel/jobs/`, `keel/audit/`, their tests, and jobs/audit
documentation.

**Out of scope:**

| Thing | Owner |
|---|---|
| AI or document-processing workflows | Brein |
| A new job runner, queue, or scheduler | Nothing is wrong with the current one |
| `keel/files`, `keel/billing` | Phases 13 and 14, concurrent |

**No migrations** unless provenance genuinely requires a field, in which
case one migration, and say so.

## Work

**1. Verify, honestly.** Confirm each claim above against the code, and
report anything that turns out weaker than advertised. Add the tests that
are genuinely missing — job failure and retry visibility, dead-letter
handling, and the "exactly one audit row per call, on commit" property under
transaction rollback.

**2. Provenance hooks.** The one genuinely new thing. Future document
ingestion needs to answer "what produced this row, from what input, by which
job run". Design the smallest thing that answers it: a nullable link from a
produced record back to the job run and its input, expressible by any app
without `keel/jobs` knowing about them. Do not build ingestion — build the
hook and demonstrate it on the demo job.

**3. `docs/jobs-and-audit.md`.** What belongs in Keel versus a product. How
to add a job (tasks take IDs, never model instances — say why). How
idempotency and concurrency control work and when each applies. How to make
a service audited, and when `@not_audited` is legitimate. How provenance
attaches.

## Acceptance — evidence required

- [ ] Every claim in "Read this first" verified against the code, with anything weaker reported
- [ ] Job failure, retry and dead-letter paths each tested and visible in the UI
- [ ] An audited service writes exactly one audit row, on commit, and **none** on rollback — tested
- [ ] The audit meta-test still bites: strip a decorator, paste the failure, restore
- [ ] Provenance hook exists, is demonstrated on the demo job, and does not require `keel/jobs` to import any consumer
- [ ] `docs/jobs-and-audit.md` written
- [ ] No AI or document-processing functionality in the diff

## Report back

What was already true; what was not; the provenance design and why it is the
smallest thing that works.
