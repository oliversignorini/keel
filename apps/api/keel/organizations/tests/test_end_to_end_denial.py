"""Acceptance: "A denial reaches the client as a 403 whose ``code`` is the
``Decision.reason``, verified end to end for one role denial and one
state denial" (phase-3.md, Acceptance; PRD §8 Phase 3).

``HasOrgPermission.has_permission`` calls ``has_perm`` with no
``subject`` (it runs before any row is loaded), so a *state* denial —
one that depends on inspecting a subject, like "cannot remove the last
owner" — has to be raised by the action itself once it has the row. This
is exactly what ``p3-orgs-api``'s real ``MembersViewSet.destroy()`` will
do; the fixture viewset below proves the plumbing (guard → ``Decision``
→ ``PermissionDeniedWithReason`` → error envelope) works end to end
before that viewset exists.
"""

import pytest
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from keel.accounts.models import User
from keel.core.authz import OrgScopedViewSet, has_perm
from keel.core.exceptions import PermissionDeniedWithReason
from keel.organizations.models import Membership, Organization, Role
from keel.organizations.permissions import Perm

pytestmark = pytest.mark.django_db


def _factory(organization: Organization) -> Membership:
    role = Role.objects.create(name="Fixture role", permissions=[])
    user = User.objects.create_user(email=f"row-{organization.pk}@example.com", password="x")
    return Membership.objects.create(
        organization=organization, user=user, role=role, status=Membership.STATUS_ACTIVE
    )


class _RoleDenialViewSet(OrgScopedViewSet):
    """Role denial: the actor's role simply lacks the required code."""

    required_permissions = (Perm.ORG_DELETE,)
    organization_scoped = True
    test_factory = f"{__name__}._factory"

    def list(self, request, *args, **kwargs):
        return Response({"ok": True})


class _StateDenialViewSet(OrgScopedViewSet):
    """State denial: the actor holds the code, but the subject-inspecting
    guard denies based on the row's state (the last-owner rule)."""

    required_permissions = (Perm.MEMBERS_REMOVE,)
    organization_scoped = True
    test_factory = f"{__name__}._factory"

    def destroy(self, request, *args, **kwargs):
        target = Membership.objects.get(pk=kwargs["pk"], organization=self.organization)
        decision = has_perm(request.user, self.organization, Perm.MEMBERS_REMOVE, subject=target)
        if not decision.allowed:
            raise PermissionDeniedWithReason(code=decision.reason, details=decision.details)
        return Response(status=204)


def _org_and_settings(settings, org_slug: str = "acme") -> Organization:
    creator = User.objects.create_user(email="creator@example.com", password="x")
    org = Organization.objects.create(name="Acme", slug=org_slug, created_by=creator)
    settings.KEEL_ORGANIZATION_RESOLVER = "keel.organizations.resolvers.resolve_organization"
    return org


def test_role_denial_reaches_client_as_403_with_reason_as_code(settings) -> None:
    org = _org_and_settings(settings)
    role = Role.objects.create(name="No-permissions role", permissions=[])
    actor = User.objects.create_user(email="actor@example.com", password="x")
    Membership.objects.create(
        organization=org, user=actor, role=role, status=Membership.STATUS_ACTIVE
    )

    request = APIRequestFactory().get(f"/fake/{org.slug}/things/")
    request.user = actor
    view = _RoleDenialViewSet.as_view({"get": "list"})

    response = view(request, org_slug=org.slug)
    response.render()

    assert response.status_code == 403
    assert response.data["error"]["code"] == "insufficient_role"


def test_state_denial_reaches_client_as_403_with_reason_as_code(settings) -> None:
    org = _org_and_settings(settings, org_slug="acme-2")
    owner_role = Role.objects.create(
        name="Owner-like role", permissions=[Perm.MEMBERS_REMOVE, Perm.ORG_TRANSFER]
    )
    sole_owner = User.objects.create_user(email="owner@example.com", password="x")
    sole_owner_membership = Membership.objects.create(
        organization=org, user=sole_owner, role=owner_role, status=Membership.STATUS_ACTIVE
    )

    request = APIRequestFactory().delete(f"/fake/{org.slug}/members/{sole_owner_membership.pk}/")
    request.user = sole_owner
    view = _StateDenialViewSet.as_view({"delete": "destroy"})

    response = view(request, org_slug=org.slug, pk=str(sole_owner_membership.pk))
    response.render()

    assert response.status_code == 403
    assert response.data["error"]["code"] == "cannot_remove_last_owner"
    assert response.data["error"]["details"] == {"membership_id": str(sole_owner_membership.pk)}
