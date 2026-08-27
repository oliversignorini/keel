# ADR 0001 — Move the API layer from DRF to Django Ninja

**Status:** Accepted — 2026-08-27
**Decides:** the open checklist item on Notion "Keel Phase 10 — Architecture review and implementation plan": _"Record an ADR: use Django Ninja instead of DRF for Keel's API layer, or explicitly reject if migration cost is too high."_
**Implemented by:** `docs/plans/phase-10.md`

---

## Context

Keel's API layer is Django REST Framework. That was never argued for in
`keel-prd.md` — §2 selects the stack and DRF arrives with it, unexamined.
The architecture direction proposal reopened it, on the grounds that Ninja's
Pydantic schemas and native type hints are a better fit for a template whose
whole selling point is that the TypeScript client is generated, never
hand-written, and that a drifted client is a build error.

The direction note framed it conditionally: prefer Ninja _unless repo
inspection shows the migration cost is too high_. This ADR records the
inspection and the decision that followed it.

## What the inspection found

Measured on `master` at `14f7808`:

| Surface                                       | Size                        |
| --------------------------------------------- | --------------------------- |
| Files importing `rest_framework`              | 43                          |
| `rest_framework` import/reference sites       | 79                          |
| Production viewsets and `APIView` subclasses  | 19, across 7 apps           |
| Python test files                             | 70                          |
| Generated TypeScript client                   | 11,229 lines across 2 files |
| `@keel/api-client` import sites in `apps/web` | 41                          |

The count is not the interesting part. Four pieces of DRF are load-bearing
for things Keel advertises as invariants, and each has to be rebuilt rather
than ported:

1. **`keel/core/authz.py`.** `GlobalViewSet` and `OrgScopedViewSet` subclass
   DRF's `GenericViewSet`; `HasOrgPermission` is a DRF `BasePermission`;
   organisation resolution hangs off DRF's `initial()` hook and queryset
   filtering off `get_queryset()`. Ninja has no viewsets, no
   `permission_classes`, and no `initial()`. The class hierarchy is the
   thing being replaced, and the `__init_subclass__` registries hanging off
   it (`registered_global_viewsets`, `registered_scoped_viewsets`) are what
   make invariants 2 and 7 enforceable at all.

2. **The tenant-isolation meta-test.** `keel/organizations/tests/tenant_isolation.py`
   walks a DRF router's `.registry` of `(prefix, viewset, basename)` tuples
   and drives the `retrieve` action through `APIRequestFactory`. Ninja
   exposes `path_operations` on a `Router`, keyed differently, with no
   action concept. `test_meta_router_wiring.py` walks the same structure.
   Both meta-tests are rewrites, not edits.

3. **`keel/core/pagination.py`.** It subclasses DRF's `CursorPagination`
   specifically because DRF's cursor encodes a within-tie offset alongside
   the ordering value, so a page boundary landing inside a run of equal
   sort values neither skips nor repeats rows. `django-ninja`'s bundled
   paginators offer limit/offset and page-number only. There is no cursor
   paginator to switch to; the tie-safe behaviour has to be reimplemented
   and re-proved.

4. **The OpenAPI → client pipeline.** `scripts/merge_openapi.py` builds the
   drf-spectacular document in-process and merges it with allauth headless's
   own spec; `packages/api-client` generates from the merged file; CI fails
   on any drift. Ninja generates its own schema with different operation IDs
   and different component-schema names, so the merged document changes
   shape, the generated client's exported symbols change, and the 41 import
   sites in `apps/web` change with them.

Two further couplings are smaller but real: `keel/core/exceptions.py` is a
DRF exception handler over `APIException` subclasses, and throttling
(`DEFAULT_THROTTLE_CLASSES`, asserted by `tests/test_rate_limiting.py`) is
DRF's, with Retry-After behaviour the error envelope depends on.

## Decision

**Migrate to Django Ninja.** Django remains the app, auth, ORM, admin and
jobs authority; Ninja becomes the typed API layer. DRF is removed from the
dependency manifest when the migration completes, not before.

The migration is its own phase (`docs/plans/phase-10.md`) and is a
serialisation point: while it runs, no other worktree may add or change a
view, serializer, route, or generated-client call site.

## The argument against, recorded

This ADR was written after an explicit recommendation to keep DRF and record
a rejection instead. The case against migrating, so it is not lost:

- The cost lands squarely on the machinery that makes Keel credible — the
  invariant meta-tests, the permission registry integration, the cursor
  paginator, the client-drift gate. Those are the parts a reader is meant to
  be impressed by, and they are the parts most likely to come back weaker.
- Nothing user-visible improves. The error envelope, URL shapes, auth model,
  and generated-client ergonomics are specified in the PRD and must survive
  unchanged, so the migration's success criterion is literally "nothing
  changed".
- A half-finished migration is worse than either endpoint. Two API idioms in
  one template is exactly the incoherence a boilerplate exists to prevent.

The decision to proceed anyway was taken deliberately, for reasons the
inspection does not measure: Ninja's Pydantic-native schemas remove the
serializer/type duplication that DRF forces, the typed signatures are a
better demonstration of the judgement Keel is meant to show, and doing it
now — before the template mechanics phase freezes the structure, and before
Brein is built on top — is the cheapest this will ever be.

## Consequences

- Phase 10 is inserted ahead of auth hardening, storage, billing polish, and
  jobs/audit work, all of which touch views and would otherwise be written
  twice.
- Template mechanics (`scripts/init.ts`) moves to the end of the sequence.
  It rewrites every file in the repo; running it against a structure that is
  about to change wastes the work.
- The phase carries an explicit abort condition. If, after the core
  primitives and the first migrated app, the invariant meta-tests cannot be
  made to hold with equal force, the correct outcome is to stop, revert, and
  supersede this ADR — not to weaken the invariants to fit the framework.
- `keel-prd.md` §2 gains a revision note; DRF is no longer the selected API
  layer.

## Alternatives considered

**Keep DRF, reject Ninja.** Cheapest, and the migration cost falls on the
best parts of the codebase. Rejected — see above.

**Spike one endpoint in Ninja, then decide.** Resolves the question with
evidence for roughly the cost of Phase 10.A alone. Rejected as a decision
procedure, but its content survives: Phase 10.A _is_ that spike, and it
carries the abort condition above.

**Run Ninja alongside DRF for new endpoints only.** Rejected outright. Two
API idioms in one template defeats the purpose of a template.
