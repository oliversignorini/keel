"""Views (PRD §7; CLAUDE.md's per-app file shape). THIN: parse, call
service, serialize, return. ``__Resource__Resource`` declares
``required_permissions``, ``organization_scoped = True``, ``test_factory``
and ``detail_url_template`` — the tenant-isolation meta-test then walks
this resource automatically (CLAUDE.md invariant 6), which is what proves
the route is actually mounted and not merely declared.
"""

from typing import Any

from ninja import Status

from keel.__app__ import selectors, services
from keel.__app__.models import __Resource__
from keel.__app__.schemas import __Resource__In, __Resource__Out, __Resource__PatchIn
from keel.core.authz import OrgScopedResource, keel_router, resolve_and_authorize
from keel.core.pagination import Page, paginate
from keel.core.selectors import get_scoped_or_404
from keel.organizations.permissions import Perm

# The permission code each action requires, named once here rather than
# inline at five call sites: a project that wants coarser permissions than
# the generated four-code CRUD scheme changes this block and nothing else.
# keel:if crud_permissions
_VIEW = Perm.__RESOURCE___VIEW
_CREATE = Perm.__RESOURCE___CREATE
_UPDATE = Perm.__RESOURCE___UPDATE
_DELETE = Perm.__RESOURCE___DELETE
# keel:endif
# keel:if manage_permissions
_VIEW = Perm.__RESOURCES___VIEW
_CREATE = Perm.__RESOURCES___MANAGE
_UPDATE = Perm.__RESOURCES___MANAGE
_DELETE = Perm.__RESOURCES___MANAGE
# keel:endif


class __Resource__Resource(OrgScopedResource):
    """``/orgs/<org_slug>/__resources__/`` — the org-scoped CRUD endpoint
    for ``__Resource__``."""

    router = keel_router(tags=["__resources__"])
    organization_scoped = True
    test_factory = "keel.__app__.tests.factories.__resource___factory"
    required_permissions = (_VIEW,)
    detail_url_template = "/api/v1/orgs/{org_slug}/__resources__/{id}/"


router = __Resource__Resource.router


@router.get(
    "/{org_slug}/__resources__/", response=Page[__Resource__Out], operation_id="list__Resources__"
)
def list___resources__(
    request: Any, org_slug: str, cursor: str | None = None, limit: int | None = None
) -> dict:
    organization = resolve_and_authorize(request, org_slug, (_VIEW,))
    queryset = selectors.list___resources__(organization)
    return paginate(request, queryset)


@router.post(
    "/{org_slug}/__resources__/",
    response={201: __Resource__Out},
    operation_id="create__Resource__"
)
def create___resource__(
    request: Any, org_slug: str, payload: __Resource__In
) -> Status[__Resource__]:
    organization = resolve_and_authorize(request, org_slug, (_CREATE,))
    __resource__ = services.create___resource__(
        organization=organization,
        created_by=request.auth,
        # keel:insert create_call_args
    )
    return Status(201, __resource__)


@router.get(
    "/{org_slug}/__resources__/{id}/",
    response=__Resource__Out,
    operation_id="retrieve__Resource__"
)
def retrieve___resource__(request: Any, org_slug: str, id: str) -> __Resource__:
    organization = resolve_and_authorize(request, org_slug, (_VIEW,))
    return get_scoped_or_404(selectors.list___resources__(organization), id)


# PATCH only — every field is optional and only the fields present in the
# body are changed. PUT is deliberately absent rather than given real
# replace-the-whole-resource semantics: a partial-update body under PUT
# would advertise idempotent-by-substitution behaviour it doesn't have,
# and two methods sharing one operationId makes PATCH unreachable from the
# generated TypeScript client (orval keeps whichever method it resolves
# the collision to).
@router.patch(
    "/{org_slug}/__resources__/{id}/",
    response=__Resource__Out,
    operation_id="update__Resource__"
)
def update___resource__(
    request: Any, org_slug: str, id: str, payload: __Resource__PatchIn
) -> __Resource__:
    organization = resolve_and_authorize(request, org_slug, (_UPDATE,))
    __resource__ = get_scoped_or_404(selectors.list___resources__(organization), id)
    fields = payload.dict(exclude_unset=True)
    return services.update___resource__(
        __resource__=__resource__,
        actor=request.auth,
        impersonator=getattr(request, "impersonator", None),
        **fields,
    )


@router.delete(
    "/{org_slug}/__resources__/{id}/", response={204: None}, operation_id="delete__Resource__"
)
def destroy___resource__(request: Any, org_slug: str, id: str) -> Status[None]:
    organization = resolve_and_authorize(request, org_slug, (_DELETE,))
    __resource__ = get_scoped_or_404(selectors.list___resources__(organization), id)
    services.delete___resource__(
        __resource__=__resource__,
        actor=request.auth,
        impersonator=getattr(request, "impersonator", None)
    )
    return Status(204, None)
