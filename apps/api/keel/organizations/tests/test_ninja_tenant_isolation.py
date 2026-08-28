"""Meta-test 2 (PRD §4 invariant 7): proves
``ninja_tenant_isolation.assert_cross_org_404`` catches a 403-not-404
leak, then runs the real thing over every production
``OrgScopedResource``.
"""

import pytest

from keel.organizations.tests.ninja_tenant_isolation import (
    assert_cross_org_404,
    production_scoped_resources,
    resource_route_is_wired,
)
from keel.organizations.tests.ninja_tenant_isolation_fixtures import (
    LeakyResource,
    WellScopedResource,
)

pytestmark = pytest.mark.django_db

_fixture_urlconf = pytest.mark.urls("keel.organizations.tests.urls_ninja_tenant_fixture")


# --- The mechanism, proven directly (fixture-only URLconf) ---------------


@_fixture_urlconf
def test_assert_cross_org_404_passes_for_a_well_scoped_resource() -> None:
    assert_cross_org_404(WellScopedResource)


@_fixture_urlconf
def test_assert_cross_org_404_fails_for_a_leaky_resource() -> None:
    with pytest.raises(AssertionError, match="403"):
        assert_cross_org_404(LeakyResource)


@_fixture_urlconf
def test_resource_route_is_wired_true_for_a_mounted_resource() -> None:
    assert resource_route_is_wired(WellScopedResource) is True


# --- The real thing: every production OrgScopedResource, real URLconf ----


def test_every_production_ninja_resource_is_wired_and_enforces_cross_org_404() -> None:
    # Resources register themselves at import time (__init_subclass__),
    # so the registry is only as complete as whatever has been imported
    # so far — force the real URLconf to load first, so this doesn't
    # silently under-report when run in isolation from other test files.
    from django.urls import get_resolver

    _ = get_resolver().url_patterns

    resources = production_scoped_resources()
    assert resources, (
        "No production OrgScopedResource exists — if this fires, a "
        "resource failed to import or register."
    )
    for resource_cls in resources:
        assert resource_route_is_wired(resource_cls), (
            f"{resource_cls.__name__}'s detail_url_template does not resolve "
            "against the live URLconf — it is declared but not mounted "
            "(PRD §4 invariant 7's 'the exemption list is where leaks hide' "
            "applies to an unmounted router too)."
        )
        assert_cross_org_404(resource_cls)
