"""Meta-test 2's missing half (PRD §4 invariant 7): a scoped viewset must
be *reachable* by the tenant-isolation walk, not merely well-formed.

``test_router_enforces_cross_org_404_for_every_scoped_viewset`` in
``test_tenant_isolation.py`` is honest about being vacuous today — it
walks ``settings.KEEL_API_ROUTER``, which is empty until a later
worktree points it at a real router. Nothing stops that from staying
empty forever: if ``p3-orgs-api`` never wires ``KEEL_API_ROUTER``, that
walk keeps skipping silently while real ``organization_scoped``
viewsets go unchecked — exactly the "the exemption list is where leaks
hide" failure mode invariant 7 exists to prevent, just for a router
instead of a justification list.

This closes that gap. ``keel.core.authz.registered_scoped_viewsets()``
records every well-formed ``OrgScopedViewSet`` subclass unconditionally,
via ``__init_subclass__`` — a scoped viewset cannot be defined without
landing there. The moment ``p3-orgs-api`` (or any other app) writes its
first production scoped viewset, this test starts failing until that
viewset is registered on ``settings.KEEL_API_ROUTER`` — CI then *demands*
the router be wired, rather than trusting someone to remember.

Test-fixture viewsets (this worktree's own, and Phase 1's in
``keel/core/tests/test_authz.py``) are excluded by module path — anything
whose ``__module__`` has a ``tests`` package segment is a fixture, not a
production viewset, and was never meant to be reachable from a real API
router.
"""

from typing import Any

from django.conf import settings
from django.utils.module_loading import import_string

from keel.core.authz import OrgScopedViewSet, registered_scoped_viewsets
from keel.organizations.tests.tenant_isolation import iter_org_scoped_viewsets


def _is_production_module(viewset_cls: type) -> bool:
    return "tests" not in viewset_cls.__module__.split(".")


def _production_scoped_viewsets() -> list[type[OrgScopedViewSet]]:
    return [cls for cls in registered_scoped_viewsets() if _is_production_module(cls)]


def _router_reachable_viewsets() -> set[type[OrgScopedViewSet]]:
    router_path = getattr(settings, "KEEL_API_ROUTER", "")
    if not router_path:
        return set()
    router: Any = import_string(router_path)
    return set(iter_org_scoped_viewsets(router))


def test_every_production_scoped_viewset_is_reachable_by_the_router() -> None:
    production_viewsets = _production_scoped_viewsets()
    if not production_viewsets:
        # Nothing to check yet — no worktree has written a production
        # scoped viewset. This is the one legitimate reason for this
        # test to pass without a router configured; see module docstring.
        return

    reachable = _router_reachable_viewsets()
    unreachable = sorted(
        (cls for cls in production_viewsets if cls not in reachable),
        key=lambda cls: cls.__qualname__,
    )

    assert not unreachable, (
        "The following organization_scoped viewset(s) exist but are not "
        "reachable by the tenant-isolation meta-test (PRD §4 invariant 7), "
        "because settings.KEEL_API_ROUTER is unset or does not register "
        "them: "
        f"{[f'{cls.__module__}.{cls.__qualname__}' for cls in unreachable]}. "
        "Register every organization_scoped viewset on the router at "
        "settings.KEEL_API_ROUTER — until then, the cross-org 404 "
        "guarantee for these viewsets is never actually checked by CI."
    )
