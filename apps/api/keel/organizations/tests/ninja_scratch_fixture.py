"""Stage 10.A's scratch endpoint (docs/plans/phase-10.md 10.A stage gate:
"10.A is done when a scratch endpoint exercises all of the above").

Lives under ``keel.organizations.tests`` rather than ``keel.core`` because
it exercises the primitives against a real model (``Membership``) and
real permission codes — importing those from ``keel.core`` would violate
the "keel.core does not import keel.organizations" import-linter
contract, the same reason DRF's own fixture viewsets
(``test_tenant_isolation.py``'s ``WellScopedDemoViewSet`` /
``LeakyDemoViewSet``) live here rather than in ``keel.core`` too.

Uses its own throwaway ``NinjaAPI`` instance (not the shared
``keel.core.ninja_api.api``) mounted only by
``keel/organizations/tests/urls_ninja_scratch.py``, a test-only URLconf —
so this spike never touches the real, production URL surface.

Deleted in 10.B once ``keel/widgets`` proves the same primitives for
real; ``test_ninja_scratch.py`` and ``urls_ninja_scratch.py`` are deleted
alongside it.

Route order matters: Django resolves URL patterns by path regex before
Ninja ever looks at HTTP method, so every literal path here
(``/echo/``, ``/conflict/``, ...) must be registered *before* the
catch-all ``/{pk}/`` route below it — otherwise ``/scratch/echo/`` never
reaches its own operation, because the ``{pk}`` pattern (registered
first, with only GET) would already have claimed that path and answers
405 for POST instead of falling through to the next pattern.
"""

from typing import Any

from django.http import Http404
from ninja import NinjaAPI, Schema

from keel.core import ninja_exceptions
from keel.core.ninja_authz import OrgScopedResource, keel_router, resolve_and_authorize
from keel.core.ninja_pagination import paginate
from keel.organizations.models import Membership
from keel.organizations.permissions import Perm

scratch_api = NinjaAPI(title="Keel API (10.A scratch)", version="scratch")
ninja_exceptions.register(scratch_api)


class _EchoIn(Schema):
    name: str


class ScratchResource(OrgScopedResource):
    """Fixture-shaped resource proving the primitives against a real
    model (``Membership``, which this app already owns) rather than a
    toy in-memory list."""

    router = keel_router(tags=["scratch"])
    required_permissions = (Perm.MEMBERS_VIEW,)
    test_factory = "keel.organizations.tests.factories.membership_factory"
    detail_url_template = "/api/v1/__scratch__/{org_slug}/scratch/{pk}/"


router = ScratchResource.router
scratch_api.add_router("/__scratch__", router)


@router.get("/{org_slug}/scratch/")
def list_scratch(request: Any, org_slug: str) -> dict:
    organization = resolve_and_authorize(request, org_slug, ScratchResource.required_permissions)
    queryset = Membership.objects.filter(organization=organization).order_by("-created_at", "id")
    return paginate(request, queryset, lambda m: {"id": str(m.pk)})


@router.post("/{org_slug}/scratch/echo/")
def echo(request: Any, org_slug: str, payload: _EchoIn) -> dict:
    resolve_and_authorize(request, org_slug, ScratchResource.required_permissions)
    return {"name": payload.name}


@router.get("/{org_slug}/scratch/conflict/")
def raise_conflict(request: Any, org_slug: str) -> dict:
    from keel.core.exceptions import Conflict

    resolve_and_authorize(request, org_slug, ScratchResource.required_permissions)
    raise Conflict(code="already_accepted", message="Already accepted.")


@router.get("/{org_slug}/scratch/payment-required/")
def raise_payment_required(request: Any, org_slug: str) -> dict:
    from keel.core.exceptions import PaymentRequired

    resolve_and_authorize(request, org_slug, ScratchResource.required_permissions)
    raise PaymentRequired(code="SEAT_LIMIT_EXCEEDED", message="Upgrade to add more.")


@router.get("/{org_slug}/scratch/unprocessable/")
def raise_unprocessable(request: Any, org_slug: str) -> dict:
    from keel.core.exceptions import UnprocessableEntity

    resolve_and_authorize(request, org_slug, ScratchResource.required_permissions)
    raise UnprocessableEntity(code="invalid_state_transition", message="Already finished.")


@router.get("/{org_slug}/scratch/admin-only/")
def admin_only(request: Any, org_slug: str) -> dict:
    """Requires a permission the scratch meta-test's actor deliberately
    lacks, proving authenticated-but-unpermitted answers 403 (PRD §4
    invariant 2) with the ``Decision.reason`` as the envelope's ``code``."""
    resolve_and_authorize(request, org_slug, (Perm.ORG_DELETE,))
    return {"ok": True}


@router.get("/{org_slug}/scratch/{pk}/")
def retrieve_scratch(request: Any, org_slug: str, pk: str) -> dict:
    organization = resolve_and_authorize(request, org_slug, ScratchResource.required_permissions)
    membership = Membership.objects.filter(organization=organization, pk=pk).first()
    if membership is None:
        raise Http404
    return {"id": str(membership.pk)}
