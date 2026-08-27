"""Fixture resources proving ``ninja_tenant_isolation.assert_cross_org_404``
itself works (PRD §4 invariant 7; phase-10.md 10.B) — one well-scoped,
one deliberately leaky, the direct Ninja counterpart to
``tenant_isolation.py``'s ``WellScopedDemoViewSet`` / ``LeakyDemoViewSet``
in ``test_tenant_isolation.py``.

Mounted only via ``urls_ninja_tenant_fixture.py``, a test-only URLconf —
this never touches the real, production URL surface.
"""

from typing import Any

from django.http import Http404
from ninja import NinjaAPI

from keel.core import ninja_exceptions
from keel.core.exceptions import PermissionDeniedWithReason
from keel.core.ninja_authz import OrgScopedResource, keel_router, resolve_and_authorize
from keel.organizations.models import Membership
from keel.organizations.permissions import Perm

fixture_api = NinjaAPI(title="Keel API (tenant-isolation fixture)", version="fixture")
ninja_exceptions.register(fixture_api)


class WellScopedResource(OrgScopedResource):
    """Relies only on filtering the queryset by ``organization`` — the
    correct pattern."""

    router = keel_router()
    required_permissions = (Perm.MEMBERS_VIEW,)
    test_factory = "keel.organizations.tests.factories.membership_factory"
    detail_url_template = "/api/v1/__ninja_meta_fixture__/{org_slug}/well/{id}/"


class LeakyResource(OrgScopedResource):
    """The realistic bug this meta-test exists to catch: fetches the row
    unscoped, then "protects" it with a manual permission check instead
    of letting a missing row 404 — disclosing the row's existence via a
    403 to someone outside its organisation."""

    router = keel_router()
    required_permissions = (Perm.MEMBERS_VIEW,)
    test_factory = "keel.organizations.tests.factories.membership_factory"
    detail_url_template = "/api/v1/__ninja_meta_fixture__/{org_slug}/leaky/{id}/"


@WellScopedResource.router.get("/{org_slug}/well/{id}/")
def well_scoped_retrieve(request: Any, org_slug: str, id: str) -> dict:
    organization = resolve_and_authorize(request, org_slug, WellScopedResource.required_permissions)
    membership = Membership.objects.filter(organization=organization, pk=id).first()
    if membership is None:
        raise Http404
    return {"id": str(membership.pk)}


@LeakyResource.router.get("/{org_slug}/leaky/{id}/")
def leaky_retrieve(request: Any, org_slug: str, id: str) -> dict:
    organization = resolve_and_authorize(request, org_slug, LeakyResource.required_permissions)
    membership = Membership.objects.get(pk=id)  # BUG: not scoped to `organization`
    if membership.organization_id != organization.pk:
        # BUG: should let the row 404 via a scoped lookup, not 403 here.
        raise PermissionDeniedWithReason(code="not_your_organisation")
    return {"id": str(membership.pk)}


fixture_api.add_router("/__ninja_meta_fixture__", WellScopedResource.router)
fixture_api.add_router("/__ninja_meta_fixture__", LeakyResource.router)
