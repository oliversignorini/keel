"""Views (PRD §7; docs/plans/phase-6.md 6.D; phase-10.md 10.B). THIN:
parse, call service, serialize, return. ``WidgetResource`` declares
``required_permissions``, ``organization_scoped = True``, ``test_factory``
and ``detail_url_template`` — the tenant-isolation meta-test then walks
this resource automatically (PRD §4 invariant 7).

Ninja has no per-action ``required_permissions`` dispatch the way DRF's
``initial()`` hook gave ``WidgetViewSet`` — each route calls
``resolve_and_authorize`` with the permission code its own action needs.
"""

from typing import Any

from django.http import Http404
from ninja import Status

from keel.core.ninja_authz import OrgScopedResource, keel_router, resolve_and_authorize
from keel.core.ninja_pagination import Page, paginate
from keel.organizations.permissions import Perm
from keel.widgets import selectors, services
from keel.widgets.models import Widget
from keel.widgets.schemas import WidgetIn, WidgetOut, WidgetPatchIn


class WidgetResource(OrgScopedResource):
    """``/orgs/<org_slug>/widgets/`` — the reference-slice CRUD
    endpoint (PRD §7's demo-resource route table)."""

    router = keel_router(tags=["widgets"])
    organization_scoped = True
    test_factory = "keel.widgets.tests.factories.widget_factory"
    required_permissions = (Perm.WIDGETS_VIEW,)
    detail_url_template = "/api/v1/orgs/{org_slug}/widgets/{id}/"


router = WidgetResource.router


def _get_widget_or_404(organization: Any, id: str) -> Widget:
    widget = selectors.list_widgets(organization).filter(pk=id).first()
    if widget is None:
        raise Http404
    return widget


@router.get("/{org_slug}/widgets/", response=Page[WidgetOut])
def list_widgets(request: Any, org_slug: str) -> dict:
    organization = resolve_and_authorize(request, org_slug, (Perm.WIDGETS_VIEW,))
    queryset = selectors.list_widgets(organization)
    return paginate(request, queryset)


@router.post("/{org_slug}/widgets/", response={201: WidgetOut})
def create_widget(request: Any, org_slug: str, payload: WidgetIn) -> Status[Widget]:
    organization = resolve_and_authorize(request, org_slug, (Perm.WIDGETS_MANAGE,))
    widget = services.create_widget(
        organization=organization,
        created_by=request.auth,
        name=payload.name,
        description=payload.description,
        status=payload.status,
    )
    return Status(201, widget)


@router.get("/{org_slug}/widgets/{id}/", response=WidgetOut)
def retrieve_widget(request: Any, org_slug: str, id: str) -> Widget:
    organization = resolve_and_authorize(request, org_slug, (Perm.WIDGETS_VIEW,))
    return _get_widget_or_404(organization, id)


# DRF's UpdateModelMixin registered both PUT and PATCH, routed to the same
# update()/partial_update() pair — every WidgetPatchIn field is already
# optional, so the two never behaved differently. One handler for both
# keeps that surface (stage 10.D's route-by-route diff caught PUT's
# absence as the one real gap, not just a documentation mismatch).
@router.api_operation(["PUT", "PATCH"], "/{org_slug}/widgets/{id}/", response=WidgetOut)
def update_widget(request: Any, org_slug: str, id: str, payload: WidgetPatchIn) -> Widget:
    organization = resolve_and_authorize(request, org_slug, (Perm.WIDGETS_MANAGE,))
    widget = _get_widget_or_404(organization, id)
    fields = payload.dict(exclude_unset=True)
    return services.update_widget(
        widget=widget,
        actor=request.auth,
        impersonator=getattr(request, "impersonator", None),
        **fields,
    )


@router.delete("/{org_slug}/widgets/{id}/", response={204: None})
def destroy_widget(request: Any, org_slug: str, id: str) -> Status[None]:
    organization = resolve_and_authorize(request, org_slug, (Perm.WIDGETS_MANAGE,))
    widget = _get_widget_or_404(organization, id)
    services.delete_widget(
        widget=widget, actor=request.auth, impersonator=getattr(request, "impersonator", None)
    )
    return Status(204, None)
