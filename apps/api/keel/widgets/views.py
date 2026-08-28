"""Views (PRD §7; CLAUDE.md's per-app file shape). THIN: parse, call
service, serialize, return. ``WidgetResource`` declares
``required_permissions``, ``organization_scoped = True``, ``test_factory``
and ``detail_url_template`` — the tenant-isolation meta-test then walks
this resource automatically (CLAUDE.md invariant 6), which is what proves
the route is actually mounted and not merely declared.
"""

from typing import Any

from ninja import Status

from keel.core.authz import OrgScopedResource, keel_router, resolve_and_authorize
from keel.core.pagination import Page, paginate
from keel.core.selectors import get_scoped_or_404
from keel.organizations.permissions import Perm
from keel.widgets import selectors, services
from keel.widgets.models import Widget
from keel.widgets.schemas import WidgetIn, WidgetOut, WidgetPatchIn

# The permission code each action requires, named once here rather than
# inline at five call sites: a project that wants coarser permissions than
# the generated four-code CRUD scheme changes this block and nothing else.
_VIEW = Perm.WIDGETS_VIEW
_CREATE = Perm.WIDGETS_MANAGE
_UPDATE = Perm.WIDGETS_MANAGE
_DELETE = Perm.WIDGETS_MANAGE


class WidgetResource(OrgScopedResource):
    """``/orgs/<org_slug>/widgets/`` — the org-scoped CRUD endpoint
    for ``Widget``."""

    router = keel_router(tags=["widgets"])
    organization_scoped = True
    test_factory = "keel.widgets.tests.factories.widget_factory"
    required_permissions = (_VIEW,)
    detail_url_template = "/api/v1/orgs/{org_slug}/widgets/{id}/"


router = WidgetResource.router


@router.get("/{org_slug}/widgets/", response=Page[WidgetOut], operation_id="listWidgets")
def list_widgets(
    request: Any, org_slug: str, cursor: str | None = None, limit: int | None = None
) -> dict:
    organization = resolve_and_authorize(request, org_slug, (_VIEW,))
    queryset = selectors.list_widgets(organization)
    return paginate(request, queryset)


@router.post("/{org_slug}/widgets/", response={201: WidgetOut}, operation_id="createWidget")
def create_widget(request: Any, org_slug: str, payload: WidgetIn) -> Status[Widget]:
    organization = resolve_and_authorize(request, org_slug, (_CREATE,))
    widget = services.create_widget(
        organization=organization,
        actor=request.auth,
        name=payload.name,
        description=payload.description,
        status=payload.status,
    )
    return Status(201, widget)


@router.get("/{org_slug}/widgets/{id}/", response=WidgetOut, operation_id="retrieveWidget")
def retrieve_widget(request: Any, org_slug: str, id: str) -> Widget:
    organization = resolve_and_authorize(request, org_slug, (_VIEW,))
    return get_scoped_or_404(selectors.list_widgets(organization), id)


# PATCH only — every field is optional and only the fields present in the
# body are changed. PUT is deliberately absent rather than given real
# replace-the-whole-resource semantics: a partial-update body under PUT
# would advertise idempotent-by-substitution behaviour it doesn't have,
# and two methods sharing one operationId makes PATCH unreachable from the
# generated TypeScript client (orval keeps whichever method it resolves
# the collision to).
@router.patch("/{org_slug}/widgets/{id}/", response=WidgetOut, operation_id="updateWidget")
def update_widget(request: Any, org_slug: str, id: str, payload: WidgetPatchIn) -> Widget:
    organization = resolve_and_authorize(request, org_slug, (_UPDATE,))
    widget = get_scoped_or_404(selectors.list_widgets(organization), id)
    fields = payload.dict(exclude_unset=True)
    return services.update_widget(
        widget=widget,
        actor=request.auth,
        impersonator=getattr(request, "impersonator", None),
        **fields,
    )


@router.delete("/{org_slug}/widgets/{id}/", response={204: None}, operation_id="deleteWidget")
def destroy_widget(request: Any, org_slug: str, id: str) -> Status[None]:
    organization = resolve_and_authorize(request, org_slug, (_DELETE,))
    widget = get_scoped_or_404(selectors.list_widgets(organization), id)
    services.delete_widget(
        widget=widget,
        actor=request.auth,
        impersonator=getattr(request, "impersonator", None),
    )
    return Status(204, None)
