"""``settings.KEEL_API_ROUTER`` points at ``api_registry`` below (PRD §4
invariant 7's DRF-side meta-test walk, ``tenant_isolation.py``). Empty
since phase-10.md 10.C: every production ``OrgScopedViewSet`` has
migrated to Ninja's ``OrgScopedResource`` — see
``keel.organizations.tests.ninja_tenant_isolation`` for the walk that
covers them now. Kept (rather than deleted) so
``test_every_production_scoped_viewset_is_reachable_by_the_router``
still has something to import until stage 10.E removes DRF and this
file along with it.
"""

from typing import Any


class _CombinedRegistry:
    """Exposes ``.registry`` the way a DRF router does — the shape
    ``iter_org_scoped_viewsets`` / ``iter_global_justifications`` expect."""

    def __init__(self, *routers: Any) -> None:
        self.registry = [entry for router in routers for entry in router.registry]


api_registry = _CombinedRegistry()
