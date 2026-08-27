"""Meta-test 2's Ninja half (phase-3.md A.5; PRD §4 invariant 7;
phase-10.md 10.B). Ninja counterpart to ``test_tenant_isolation.py``:
proves ``ninja_tenant_isolation.assert_cross_org_404`` catches the same
403-not-404 leak DRF's mechanism does, then runs the real thing over
every production ``OrgScopedResource`` — which today means
``keel.widgets.views.WidgetResource``, the first (and, until 10.C, only)
app migrated off DRF.
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
    # so far — force the real URLconf to load first, the way
    # tenant_isolation.py's DRF-side walk forces its router module to
    # load via import_string(settings.KEEL_API_ROUTER), so this doesn't
    # silently under-report when run in isolation from other test files.
    from django.urls import get_resolver

    _ = get_resolver().url_patterns

    resources = production_scoped_resources()
    assert resources, (
        "No production OrgScopedResource exists yet — this should start "
        "covering keel.widgets.views.WidgetResource the moment stage 10.B "
        "lands; if this fires, the resource failed to import or register."
    )
    for resource_cls in resources:
        assert resource_route_is_wired(resource_cls), (
            f"{resource_cls.__name__}'s detail_url_template does not resolve "
            "against the live URLconf — it is declared but not mounted "
            "(PRD §4 invariant 7's 'the exemption list is where leaks hide' "
            "applies to an unmounted router too)."
        )
        assert_cross_org_404(resource_cls)
