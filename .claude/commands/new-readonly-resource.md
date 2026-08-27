Generate a read-only vertical slice for the resource named in
`$ARGUMENTS` — same shape as `/new-resource` minus every write path.
Use this for reference data, computed views, or anything the API only
ever lists and retrieves (a `GlobalViewSet` with no org scoping is also
valid here if the data is genuinely global — see below).

**Ask first** whether this resource is org-scoped or global if it isn't
obvious. A resource that is legitimately identical across every tenant
(enrichment data, shared taxonomies) is a `GlobalViewSet` with a
`GLOBAL_JUSTIFICATION`; get that justification from the caller rather
than inventing one — invariant 6 requires it to be a real paragraph, not
boilerplate.

## Backend (`apps/api/keel/<app>/`)

1. `models.py`, `migrations/0001_initial.py`.
2. `selectors.py` — `list_<resource>s(...)`, `get_<resource>(...)`. No
   `services.py` is needed unless something writes this data
   out-of-band (a sync task, an import job) — if so, add `services.py`
   with `@audited`/`@not_audited` on the writer, per `/new-job` if it's
   task-driven.
3. `serializers.py` — one read serializer.
4. `views.py` — `<Resource>ViewSet(mixins.ListModelMixin,
   mixins.RetrieveModelMixin, OrgScopedViewSet)` (or `GlobalViewSet`).
   Org-scoped: `organization_scoped = True` + `test_factory`. Global:
   `organization_scoped = False` + `GLOBAL_JUSTIFICATION` naming why no
   tenant leak is possible.
5. `urls.py`, `admin.py`.

## Permissions

Add one `<RESOURCE>_VIEW` code only — no `_MANAGE`. Register it in
`organizations/permissions.py` next to the existing `_VIEW` codes, and
add it to `_MEMBER_CODES` in `roles.py`.

## Tests

- `factories.py` with a `<resource>_factory` (required even for a global
  viewset's fixture data, unless nothing ever needs to build one, which
  is unusual).
- `test_api_<app>.py` — allow-path list/retrieve test and a deny-path
  test asserting the `reason`. If org-scoped, no separate cross-org test
  is needed — the meta-tests cover it once `test_factory` is set. If
  global, write the explicit test that a viewset's id space doesn't leak
  an org-private relationship (see the pattern in PRD §4 invariant 7,
  "Where a global table has a tenant-scoped companion").

## Frontend

`page.tsx` (list) and `[id]/page.tsx` (detail) only — no `new/page.tsx`.

## Finish

`/sync-client`, then `/check-invariants`.
