"""The tenant-isolation meta-test mechanism (phase-3.md A.5; PRD §4
invariant 7). See ``test_tenant_isolation.py`` for the meta-test itself
and the proof this mechanism actually catches a leak.
"""

import uuid
from typing import Any

from django.utils.module_loading import import_string
from rest_framework.test import APIRequestFactory

from keel.accounts.models import User
from keel.core.authz import OrgScopedViewSet, registered_global_viewsets
from keel.organizations.models import Membership, Organization, Role


def iter_org_scoped_viewsets(router: Any) -> Any:
    """Every non-abstract, ``organization_scoped`` viewset registered on
    ``router`` (a DRF router or anything exposing a ``.registry`` of
    ``(prefix, viewset, basename)`` tuples), in registration order."""
    seen = set()
    for _prefix, viewset, _basename in getattr(router, "registry", []):
        if viewset in seen:
            continue
        seen.add(viewset)
        if issubclass(viewset, OrgScopedViewSet) and getattr(viewset, "organization_scoped", False):
            yield viewset


def _is_production_module(viewset_cls: type) -> bool:
    return "tests" not in viewset_cls.__module__.split(".")


def iter_global_justifications() -> Any:
    """``(viewset name, GLOBAL_JUSTIFICATION)`` for every production
    ``organization_scoped = False`` ``GlobalViewSet`` ever defined — drawn
    from ``keel.core.authz.registered_global_viewsets()``, not any
    particular router. A ``GlobalViewSet`` is recorded there unconditionally
    at import time, so its justification is printed in CI output regardless
    of which router it lands on or whether it is routed at all (PRD §4
    invariant 7). Test-fixture viewsets are excluded by module path, the
    way ``test_meta_router_wiring.py`` excludes them from the scoped-viewset
    walk: anything whose ``__module__`` has a ``tests`` package segment."""
    seen = set()
    for viewset in registered_global_viewsets():
        if viewset in seen:
            continue
        seen.add(viewset)
        if not _is_production_module(viewset):
            continue
        if not getattr(viewset, "organization_scoped", False):
            yield viewset.__name__, viewset.GLOBAL_JUSTIFICATION


def assert_cross_org_404(viewset_cls: type[OrgScopedViewSet]) -> None:
    """Build a row in organisation A via ``viewset_cls.test_factory``, and
    assert that a member of organisation B — who holds every code in
    ``viewset_cls.required_permissions`` — gets 404 from the viewset's
    ``retrieve`` action for that row, not any other status."""
    assert viewset_cls.test_factory is not None
    factory = import_string(viewset_cls.test_factory)

    creator = User.objects.create_user(
        email=f"meta-creator-{uuid.uuid4().hex[:12]}@example.com", password="s3cret-pass"
    )
    org_a = Organization.objects.create(
        name="Meta Org A", slug=f"meta-org-a-{uuid.uuid4().hex[:12]}", created_by=creator
    )
    org_b = Organization.objects.create(
        name="Meta Org B", slug=f"meta-org-b-{uuid.uuid4().hex[:12]}", created_by=creator
    )

    row_in_a = factory(org_a)

    required_permissions = list(viewset_cls.required_permissions or [])
    actor_role = Role.objects.create(name="_meta_test_actor_role", permissions=required_permissions)
    actor = User.objects.create_user(
        email=f"meta-actor-{uuid.uuid4().hex[:12]}@example.com", password="s3cret-pass"
    )
    Membership.objects.create(
        organization=org_b, user=actor, role=actor_role, status=Membership.STATUS_ACTIVE
    )

    request = APIRequestFactory().get(f"/fake/{org_b.slug}/x/{row_in_a.pk}/")
    request.user = actor
    view = viewset_cls.as_view({"get": "retrieve"})

    response = view(request, org_slug=org_b.slug, pk=str(row_in_a.pk))
    if hasattr(response, "render"):
        response.render()

    assert response.status_code == 404, (
        f"{viewset_cls.__name__}: a member of another organisation got "
        f"{response.status_code} on the detail route for a row in a "
        "different organisation — PRD §4 invariant 7 requires 404, never "
        "403 (a 403 discloses the row exists)."
    )
