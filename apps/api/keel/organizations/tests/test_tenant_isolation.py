"""Meta-test 2 (phase-3.md A.5; PRD §4 invariant 7): tenant isolation.

Walks every ``organization_scoped`` viewset registered on the DRF router
at ``settings.KEEL_API_ROUTER``, builds a row in each of two
organisations via the viewset's ``test_factory``, and asserts every
detail route returns 404 — never 403 — for a member of the other
organisation. A 403 would confirm the organisation exists to someone who
isn't in it (PRD §6 "Wrong organisation → 404 → never 403").

No worktree has registered a production router yet (``p3-orgs-api``
builds viewsets; ``KEEL_API_ROUTER`` is empty until it points one here),
so ``test_router_enforces_cross_org_404_for_every_scoped_viewset`` is
vacuous today and starts covering real viewsets the moment that setting
is filled in. The mechanism itself — ``assert_cross_org_404`` — is
proven directly below, against fixture viewsets built on ``Membership``
(a model this app owns), both for a well-behaved viewset (passes) and a
deliberately leaky one (fails with the exact 403-not-404 bug this
meta-test exists to catch: a hand-rolled cross-org check that raises
``PermissionDenied`` instead of relying on queryset scoping + the
natural ``Http404``).
"""

import pytest
from django.conf import settings
from django.utils.module_loading import import_string
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from keel.accounts.models import User
from keel.core.authz import GlobalViewSet, OrgScopedViewSet
from keel.organizations.models import Membership, Organization, Role
from keel.organizations.permissions import Perm
from keel.organizations.tests.tenant_isolation import (
    assert_cross_org_404,
    iter_global_justifications,
    iter_org_scoped_viewsets,
)

pytestmark = pytest.mark.django_db


def _membership_factory(organization: Organization) -> Membership:
    role = Role.objects.create(name="Fixture role", permissions=[Perm.MEMBERS_VIEW])
    member = User.objects.create_user(
        email=f"member-{organization.pk}@example.com", password="s3cret-pass"
    )
    return Membership.objects.create(
        organization=organization, user=member, role=role, status=Membership.STATUS_ACTIVE
    )


class WellScopedDemoViewSet(OrgScopedViewSet):
    """Relies only on ``OrgScopedViewSet.get_queryset()``'s
    ``for_organization`` filter — the correct pattern."""

    required_permissions = (Perm.MEMBERS_VIEW,)
    organization_scoped = True
    test_factory = "keel.organizations.tests.test_tenant_isolation._membership_factory"
    queryset = Membership.objects.all()

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        return Response({"id": str(obj.pk)})


class LeakyDemoViewSet(OrgScopedViewSet):
    """The realistic bug this meta-test exists to catch: fetches the row
    unscoped, then "protects" it with a manual permission check instead
    of letting a missing row 404 — disclosing the row's existence via a
    403 to someone outside its organisation."""

    required_permissions = (Perm.MEMBERS_VIEW,)
    organization_scoped = True
    test_factory = "keel.organizations.tests.test_tenant_isolation._membership_factory"
    queryset = Membership.objects.all()

    def retrieve(self, request, *args, **kwargs):
        obj = Membership.objects.get(pk=kwargs["pk"])  # BUG: not scoped to self.organization
        if obj.organization_id != self.organization.pk:
            raise PermissionDenied("not your organisation")  # BUG: should 404, not 403
        return Response({"id": str(obj.pk)})


# --- The mechanism, proven directly (no router / KEEL_API_ROUTER needed) --


def test_assert_cross_org_404_passes_for_a_well_scoped_viewset() -> None:
    assert_cross_org_404(WellScopedDemoViewSet)


def test_assert_cross_org_404_fails_for_a_leaky_viewset() -> None:
    with pytest.raises(AssertionError, match="403"):
        assert_cross_org_404(LeakyDemoViewSet)


# --- Router walking -----------------------------------------------------


class _FixtureGlobalViewSet(GlobalViewSet):
    required_permissions = (Perm.AUDIT_VIEW,)
    organization_scoped = False
    GLOBAL_JUSTIFICATION = "Fixture — reference data identical across tenants."


def test_iter_org_scoped_viewsets_finds_scoped_viewsets_on_a_router() -> None:
    router = SimpleRouter()
    router.register("widgets", WellScopedDemoViewSet, basename="fixture-widgets")
    router.register("brands", _FixtureGlobalViewSet, basename="fixture-brands")

    found = list(iter_org_scoped_viewsets(router))

    assert found == [WellScopedDemoViewSet]


def test_iter_global_justifications_excludes_test_fixture_viewsets() -> None:
    """``_FixtureGlobalViewSet`` above is well-formed and organization_scoped
    = False, so it lands in the registry — but it lives under this
    ``tests`` package, so it must not show up in CI's justification print."""
    names = {name for name, _justification in iter_global_justifications()}

    assert "_FixtureGlobalViewSet" not in names


def test_iter_global_justifications_finds_globals_from_the_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The print is driven by the registry, not by whichever router a
    viewset happens to be wired to — this is the fix for PRD §4 invariant
    7's gap: a GlobalViewSet on a router nobody walks (or on no router at
    all) must still surface its justification."""

    # Plain duck-typed stand-ins, not real GlobalViewSet/OrgScopedViewSet
    # subclasses — a real subclass would register itself in the actual,
    # process-wide registries via __init_subclass__ and leak into every
    # other test in the suite (e.g. test_meta_router_wiring.py).
    fake_global_viewset = type(
        "_ProductionGlobalViewSet",
        (),
        {
            "__module__": "keel.billing.viewsets",
            "organization_scoped": False,
            "GLOBAL_JUSTIFICATION": "Catalogue data, identical across tenants.",
        },
    )
    fake_scoped_viewset = type(
        "_ProductionScopedViewSet",
        (),
        {"__module__": "keel.billing.viewsets", "organization_scoped": True},
    )

    monkeypatch.setattr(
        "keel.organizations.tests.tenant_isolation.registered_global_viewsets",
        lambda: [fake_global_viewset, fake_scoped_viewset],
    )

    assert list(iter_global_justifications()) == [
        ("_ProductionGlobalViewSet", "Catalogue data, identical across tenants.")
    ]


def test_no_production_global_justification_is_blank() -> None:
    """A GLOBAL_JUSTIFICATION of " " satisfies __init_subclass__'s "declared
    a string" check and defeats the entire point of PRD §4 invariant 7 — an
    exemption nobody has to actually write a paragraph for. This walks the
    real registry, not a fixture."""
    blank = [
        name
        for name, justification in iter_global_justifications()
        if not (justification or "").strip()
    ]

    assert not blank, (
        "The following GlobalViewSet(s) declare a GLOBAL_JUSTIFICATION that "
        f"is missing, empty, or whitespace-only: {blank}. PRD §4 invariant "
        "7 requires a real explanation, not just a truthy string."
    )


def test_router_enforces_cross_org_404_for_every_scoped_viewset() -> None:
    """The real meta-test: walks settings.KEEL_API_ROUTER. Vacuous until a
    later worktree points it at a real router — see module docstring."""
    router_path = getattr(settings, "KEEL_API_ROUTER", "")
    if not router_path:
        pytest.skip("KEEL_API_ROUTER is not configured yet — no production router to walk.")
    router = import_string(router_path)
    for viewset_cls in iter_org_scoped_viewsets(router):
        assert_cross_org_404(viewset_cls)
