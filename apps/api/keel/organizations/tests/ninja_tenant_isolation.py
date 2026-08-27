"""The Ninja counterpart to ``tenant_isolation.py`` (PRD §4 invariant 7;
docs/plans/phase-10.md 10.B). Ninja operations are plain functions with no
``.registry`` to walk and no ``retrieve`` action to call directly — so
this drives the real, mounted URL with Django's test ``Client`` instead of
``APIRequestFactory``, which the phase-10 plan calls "closer to the truth
anyway": it goes through the actual URLconf, the real auth callable, and
the real middleware stack, not a bare view function.

``OrgScopedResource.detail_url_template`` (``keel/core/ninja_authz.py``)
is what makes this possible without introspecting Ninja's internal
routing structures: every scoped resource declares the literal URL for
its own retrieve-shaped operation.
"""

import uuid
from typing import Any

from django.test import Client
from django.urls.exceptions import Resolver404
from django.utils.module_loading import import_string

from keel.accounts.models import User
from keel.core.ninja_authz import (
    OrgScopedResource,
    registered_global_resources,
    registered_scoped_resources,
)
from keel.organizations.models import Membership, Organization, Role


def _is_production_module(resource_cls: type) -> bool:
    return "tests" not in resource_cls.__module__.split(".")


def production_scoped_resources() -> list[type[OrgScopedResource]]:
    """Every well-formed, non-abstract ``OrgScopedResource`` subclass
    outside a ``tests`` package — the Ninja equivalent of
    ``tenant_isolation.py``'s production-viewset filter."""
    return [cls for cls in registered_scoped_resources() if _is_production_module(cls)]


def iter_global_justifications() -> Any:
    """``(resource name, GLOBAL_JUSTIFICATION)`` for every production
    ``organization_scoped = False`` ``GlobalResource`` — the Ninja
    counterpart to ``tenant_isolation.py``'s DRF-side function of the
    same name, walking ``keel.core.ninja_authz.registered_global_resources()``
    instead of ``keel.core.authz.registered_global_viewsets()``."""
    seen = set()
    for resource in registered_global_resources():
        if resource in seen:
            continue
        seen.add(resource)
        if not _is_production_module(resource):
            continue
        if not getattr(resource, "organization_scoped", False):
            yield resource.__name__, resource.GLOBAL_JUSTIFICATION


def resource_route_is_wired(resource_cls: type[OrgScopedResource]) -> bool:
    """Proves the resource's ``detail_url_template`` actually resolves
    against the live URLconf — the Ninja equivalent of the DRF router
    walk, but stronger: this checks the route is *mounted*, not merely
    that a class exists somewhere declaring the right attributes."""
    from django.urls import resolve

    dummy_path = resource_cls.detail_url_template.format(  # type: ignore[union-attr]
        org_slug="dummy-org", pk=str(uuid.uuid4())
    )
    try:
        resolve(dummy_path)
    except Resolver404:
        return False
    return True


def assert_cross_org_404(resource_cls: type[OrgScopedResource]) -> None:
    """Build a row in organisation A via ``resource_cls.test_factory``,
    and assert that a member of organisation B — who holds every code in
    ``resource_cls.required_permissions`` — gets 404 from the resource's
    real, mounted detail route for that row, not any other status."""
    assert resource_cls.test_factory is not None
    factory = import_string(resource_cls.test_factory)

    creator = User.objects.create_user(
        email=f"ninja-meta-creator-{uuid.uuid4().hex[:12]}@example.com", password="s3cret-pass"
    )
    org_a = Organization.objects.create(
        name="Ninja Meta Org A",
        slug=f"ninja-meta-org-a-{uuid.uuid4().hex[:12]}",
        created_by=creator,
    )
    org_b = Organization.objects.create(
        name="Ninja Meta Org B",
        slug=f"ninja-meta-org-b-{uuid.uuid4().hex[:12]}",
        created_by=creator,
    )

    row_in_a = factory(org_a)

    required_permissions = list(resource_cls.required_permissions or [])
    actor_role = Role.objects.create(
        name="_ninja_meta_test_actor_role", permissions=required_permissions
    )
    actor = User.objects.create_user(
        email=f"ninja-meta-actor-{uuid.uuid4().hex[:12]}@example.com", password="s3cret-pass"
    )
    Membership.objects.create(
        organization=org_b, user=actor, role=actor_role, status=Membership.STATUS_ACTIVE
    )

    url = resource_cls.detail_url_template.format(  # type: ignore[union-attr]
        org_slug=org_b.slug, pk=str(row_in_a.pk)
    )
    client = Client()
    client.force_login(actor)
    response = client.get(url)

    assert response.status_code == 404, (
        f"{resource_cls.__name__}: a member of another organisation got "
        f"{response.status_code} on the detail route for a row in a "
        "different organisation — PRD §4 invariant 7 requires 404, never "
        "403 (a 403 discloses the row exists)."
    )
