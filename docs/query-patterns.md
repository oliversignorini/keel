# Query patterns

Phase 16.A. How selectors own query shape, how to keep a list endpoint at
a fixed query count regardless of row count, and how to add a
query-count test to a new endpoint.

## Selectors own query shape

Every ORM read lives in an app's `selectors.py` (PRD §4 invariant 1). A
view resolves the organisation, calls a selector, and serializes the
result — it never calls `Model.objects` itself. This is not just style:
`select_related`/`prefetch_related` decisions belong in exactly one
place per query, so fixing an N+1 means editing one function, not
auditing every call site that happens to build the same queryset.

`keel/core/selectors.py::get_scoped_or_404(queryset, pk)` is the shared
helper behind every `retrieve`/`update`/`delete` route: pass it a
queryset already narrowed to one organisation (usually an app selector's
list function) and it filters by `pk` and raises `Http404` on a miss.
This replaced twelve copy-pasted `_get_X_or_404` functions (posd#10) —
add a new one only if a route's 404 semantics genuinely differ (e.g.
`organizations.views._get_role_or_422`, which is a 422 against a
non-org-scoped table, not a tenant-boundary 404).

## Avoiding N+1s

Two shapes cover almost every case:

- **A field on every row needs a related row's data**
  (`WidgetOut.created_by`, `MembershipOut.role`): `select_related` in the
  selector that builds the list queryset.
- **A field on every row needs a _collection_ of related rows**
  (`JobOut.steps`, `PlanOut.prices`): `prefetch_related`, with a
  `Prefetch(...)` object if the related queryset needs its own
  `order_by` or filter (`keel.jobs.selectors.list_jobs_for_organization`
  prefetches `steps` ordered by `ordinal`; `keel.billing.selectors.
list_active_plans` prefetches only `is_active` prices into
  `active_prices`).

The tell that a schema resolver needs one of these: a `resolve_X`
staticmethod on a Ninja `Schema` that walks a relation
(`obj.role.name`, `obj.steps.all()`, `obj.plan.code`). If the selector
that builds the queryset doesn't already carry the matching
`select_related`/`prefetch_related`, that resolver is one query per row.
Two real examples fixed in this phase:

- `JobOut.resolve_steps` read `obj.steps.all()` — `list_jobs_for_organization`
  now prefetches `steps` (ordered by `ordinal`), so the list endpoint's
  query count no longer grows with the number of jobs.
- `SubscriptionOut.resolve_plan` read `obj.plan.code` —
  `billing.selectors.get_subscription` now `select_related("plan")`.

Passing a `status` filter argument to a selector and then re-filtering
the same queryset again in the view is the other pattern this phase
found and removed (`jobs.views.list_jobs` used to build the queryset via
`selectors.list_jobs_for_organization(organization)` — dropping the
`status` argument the selector already accepts — and then filter again
inline). If a selector takes a filter argument, pass it; don't
re-implement the filter at the call site.

## Django Debug Toolbar, locally

`django-debug-toolbar` is not currently wired into `config/settings/dev.py`.
To inspect a request's query count and SQL while developing:

```python
# config/settings/dev.py, temporarily
INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
INTERNAL_IPS = ["127.0.0.1"]
```

then add `path("__debug__/", include("debug_toolbar.urls"))` to
`config/urls.py` under `if settings.DEBUG:`. Don't commit this — it's a
local-only aid; the query-count tests below are the checked-in guard.

For a quick one-off count without the toolbar, wrap the call in a test
or a shell session with `django.test.utils.CaptureQueriesContext`:

```python
from django.db import connection
from django.test.utils import CaptureQueriesContext

with CaptureQueriesContext(connection) as ctx:
    client.get(url)
print(len(ctx), [q["sql"] for q in ctx.captured_queries])
```

## Adding a query-count test to a new endpoint

Follow `keel/widgets/tests/test_query_counts.py` (the reference slice) or
any of the other six added in this phase:

1. Build a small org, an authenticated owner client, and **more than
   one** row of whatever the endpoint lists (an N+1 doesn't show up
   with a single row — a fixed query count on 3 rows is the whole
   point).
2. Wrap the request in `django_assert_num_queries(N)` — `N` starts as a
   guess; run the test with `-vv` to see the actual count and the SQL
   for each query when it fails, then pin `N` to the real number.
3. Write a one-line comment per query explaining what it's for. A bare
   `assertNumQueries(4)` nobody can justify gets bumped to 5 the first
   time it fails, which defeats the point — the comment is what lets a
   reviewer tell "this grew because of a real new join" from "this grew
   because someone forgot select_related".
4. Every endpoint here costs 3 queries before it does anything
   endpoint-specific: session → session key, session key → `User`,
   `org_slug` → `Organization` via an active `Membership` join. A fourth
   (`has_perm`'s `Membership`+`Role` lookup) is added by every
   `resolve_and_authorize` call. Budget for those four before counting
   what the endpoint's own selector adds.

The seven endpoints this phase pinned:

| Endpoint                                 | Test                                                                            | Query count |
| ---------------------------------------- | ------------------------------------------------------------------------------- | ----------- |
| `GET /me/`                               | `organizations/tests/test_query_counts.py::test_me_query_count`                 | 5           |
| `GET /orgs/`                             | `organizations/tests/test_query_counts.py::test_list_organizations_query_count` | 3           |
| `GET /orgs/<slug>/members/`              | `organizations/tests/test_query_counts.py::test_list_members_query_count`       | 5           |
| `GET /orgs/<slug>/widgets/`              | `widgets/tests/test_query_counts.py::test_list_widgets_query_count`             | 5           |
| `GET /orgs/<slug>/audit/`                | `audit/tests/test_query_counts.py::test_list_audit_logs_query_count`            | 5           |
| `GET /orgs/<slug>/files/`                | `files/tests/test_query_counts.py::test_list_files_query_count`                 | 5           |
| `GET /orgs/<slug>/billing/subscription/` | `billing/tests/test_query_counts.py::test_get_subscription_query_count`         | 5           |

(`GET /orgs/<slug>/jobs/` isn't one of the seven named in the phase plan
but was added too — `jobs/tests/test_query_counts.py`, 6 queries, the
extra one being the `steps` prefetch.)

## Index audit

The cursor paginator's default ordering is `("-created_at", "id")`
(`keel/core/pagination.py`); a route that overrides `ordering`
needs the matching composite index instead. Checked against every
paginated model:

| Model                              | Pages on                                                                                                                                        | Index                                                | Status                                                                                                                                                                          |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Widget`                           | `(-created_at, id)`                                                                                                                             | `(organization, created_at)`                         | ✓                                                                                                                                                                               |
| `FileUpload`                       | `(-created_at, id)`                                                                                                                             | `(organization, created_at)`                         | ✓                                                                                                                                                                               |
| `Membership`                       | `(-created_at, id)`                                                                                                                             | `(organization, created_at)`                         | ✓                                                                                                                                                                               |
| `Invitation`                       | `(-created_at, id)`                                                                                                                             | `(organization, created_at)`                         | ✓                                                                                                                                                                               |
| `Job`                              | `(-created_at, id)`                                                                                                                             | `(organization, created_at)`                         | ✓                                                                                                                                                                               |
| `AuditLog`                         | `(-id,)` (ddia#18 — UUIDv7 `id` is monotonic and already unique; `created_at` isn't, for two causally-ordered writes racing across app servers) | `(organization, created_at)` only, before this phase | **gap — fixed**: added `(organization, id)` in `keel/audit/migrations/0002_audit_log_organization_id_index.py`                                                                  |
| `Plan`                             | `(sort_order, code)`                                                                                                                            | none                                                 | audited, not added — catalogue data, expected row count in the single digits (one row per pricing tier); a sequential scan over the whole table costs less than the index would |
| `Organization` (`GET /orgs/`)      | `name`                                                                                                                                          | none                                                 | audited, not added — bounded by the requesting user's own membership count via the join, not by table size                                                                      |
| `Role` (`GET /orgs/<slug>/roles/`) | `(-created_at, id)` default                                                                                                                     | none beyond the FK's own index                       | audited, not added — three global presets plus feature-flagged (off by default) custom roles per org; not a table that grows                                                    |

Every `OrgScopedModel` subclass gets `organization` indexed by default
(`db_index=True` on the FK, `keel/core/models.py`); the table above is
about the _composite_ index a paginated ordering needs on top of that,
not the base tenant-scoping index.
