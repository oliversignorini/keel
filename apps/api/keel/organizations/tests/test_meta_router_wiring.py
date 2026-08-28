"""Meta-test 2's missing half (PRD §4 invariant 7): a scoped resource must
be *reachable* by the tenant-isolation walk, not merely well-formed.

``keel.core.authz.registered_scoped_resources()`` records every
well-formed ``OrgScopedResource`` subclass unconditionally, via
``__init_subclass__`` — a scoped resource cannot be defined without landing
there. If one is declared but its router is never mounted in
``config/urls.py``, the cross-org 404 guarantee for it is never actually
checked by CI: exactly the "the exemption list is where leaks hide"
failure mode invariant 7 exists to prevent, just for an unmounted router
instead of a justification list. This test fails until it is mounted.

Test-fixture resources are excluded by module path — anything whose
``__module__`` has a ``tests`` package segment is a fixture, not a
production resource, and was never meant to be reachable from the real
URLconf.
"""

from django.urls import get_resolver

from keel.core.authz import OrgScopedResource
from keel.organizations.tests.ninja_tenant_isolation import (
    production_scoped_resources,
    resource_route_is_wired,
)


def test_every_production_ninja_resource_is_reachable_by_the_router() -> None:
    _ = get_resolver().url_patterns  # force config.urls (and its routers) to load

    production_resources: list[type[OrgScopedResource]] = production_scoped_resources()
    unreachable = sorted(
        (cls for cls in production_resources if not resource_route_is_wired(cls)),
        key=lambda cls: cls.__qualname__,
    )

    assert not unreachable, (
        "The following OrgScopedResource(s) exist but their "
        "detail_url_template does not resolve against the live URLconf "
        "(PRD §4 invariant 7): "
        f"{[f'{cls.__module__}.{cls.__qualname__}' for cls in unreachable]}. "
        "Mount the resource's router in config/urls.py — until then, the "
        "cross-org 404 guarantee for these resources is never actually "
        "checked by CI."
    )
