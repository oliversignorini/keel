Generate a full CRUD vertical slice for the resource named in `$ARGUMENTS`
(a singular PascalCase model name, e.g. `Invoice`). Copy the shape of
`apps/api/keel/widgets/` — the reference slice — file for file. Do not
invent a different structure.

**Ask first** if the app name (usually the lowercase plural of the
resource, e.g. `invoices`) isn't obvious from `$ARGUMENTS`, or if the
resource needs fields beyond `name`/`description`/`status` — get the field
list before generating.

## Backend (`apps/api/keel/<app>/`)

1. `models.py` — the model, `organization` FK required, data shape only.
2. `migrations/0001_initial.py` — `makemigrations`, don't hand-write it.
3. `selectors.py` — `list_<resource>s(organization)`, `get_<resource>(organization, id)`. Reads only.
4. `services.py` — `create_<resource>`, `update_<resource>`, `delete_<resource>`.
   Each mutating function is `@audited("<resource>.created")` etc. (import
   from `keel.core.audit`). One `transaction.atomic()` per function,
   opened here. Follow `widgets/services.py`'s pattern for a Tier-1
   dispatch on `transaction.on_commit()` if the resource needs one.
5. `serializers.py` — a read `<Resource>Serializer`, a write
   `<Resource>WriteSerializer`, an update `<Resource>UpdateSerializer`.
6. `views.py` — `<Resource>ViewSet(mixins..., OrgScopedViewSet)` from
   `keel.core.authz`. Set `organization_scoped = True` and
   `test_factory = "keel.<app>.tests.factories.<resource>_factory"`.
   Declare `_ACTION_PERMISSIONS` per action, thin methods that call
   `selectors`/`services` only.
7. `urls.py` — register on the org-scoped router, matching
   `widgets/urls.py`'s pattern.
8. `tasks.py` — one-line delegations only, if the service dispatches one.
9. `admin.py` — register the model.

## Permissions (`apps/api/keel/organizations/permissions.py` — the only
file allowed to add these)

- Add `<RESOURCE>_VIEW` and `<RESOURCE>_MANAGE` codes to `Perm`.
- `registry.register(Perm.<RESOURCE>_VIEW, _role_guard(Perm.<RESOURCE>_VIEW))`
  and the `_MANAGE` equivalent, next to the existing `WIDGETS_*` lines.
- Add both codes to `_MEMBER_CODES` in `roles.py` (Member gets view +
  manage on domain resources, per the comment there) unless told otherwise.

## Tests (`apps/api/keel/<app>/tests/`)

- `factories.py` — a `factory_boy` factory, exported as
  `<resource>_factory` (the string the viewset's `test_factory` points at).
- `test_models.py`, `test_services.py` — allow and failure paths.
- `test_api_<app>.py` — one allow-path test and one deny-path test per
  action, asserting the `Decision.reason` on denial per invariant 2's
  coverage rule, not just the status code.
- Do **not** hand-write a cross-org test — `test_meta_router_wiring.py`
  and `test_tenant_isolation.py` already walk every viewset that declares
  `test_factory`.

## Frontend (`apps/web/app/(app)/app/[org]/<app>/`)

- `page.tsx` (list), `new/page.tsx` (create), `[id]/page.tsx` (detail),
  matching `widgets/`'s three files. Use the generated client from
  `packages/api-client` — call `/sync-client` first if the OpenAPI spec
  needs regenerating to pick up the new endpoints.

## Finish

1. Run `cd apps/api && uv run python manage.py makemigrations` for the
   model, then `makemigrations --check --dry-run` to confirm it's clean.
2. Run `/sync-client` to regenerate the TS client against the new routes.
3. Run `/check-invariants` and fix anything it reports before considering
   this done — an output that fails `/check-invariants` is not a finished
   `/new-resource` run.
