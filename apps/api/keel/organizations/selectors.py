"""Reads (PRD §4, "Data model"; phase-3.md B.2).

Services mutate and return; this module queries and returns. Nothing here
writes.
"""

from typing import Any
from uuid import UUID

from django.db.models import Q, QuerySet

from keel.core.authz import registry
from keel.organizations.models import Invitation, Membership, Organization, Role


def list_organizations_for_user(user: Any) -> QuerySet[Organization]:
    return (
        Organization.objects.filter(
            deleted_at__isnull=True,
            membership__user=user,
            membership__status=Membership.STATUS_ACTIVE,
        )
        .distinct()
        .order_by("name")
    )


def get_membership(*, user: Any, organization: Organization) -> Membership | None:
    return (
        Membership.objects.filter(
            organization=organization, user=user, status=Membership.STATUS_ACTIVE
        )
        .select_related("role")
        .first()
    )


def get_active_memberships_by_organization(
    *, user: Any, organizations: Any
) -> dict[Any, Membership]:
    """One query for every organisation's membership, keyed by
    ``organization_id`` — the bulk counterpart to ``get_membership``.

    ``GET /api/v1/me/`` (api-patterns finding 12) used to call
    ``get_membership`` once per organisation in a Python loop, an N+1 that
    scales with how many organisations a user belongs to. A single
    ``organization__in`` query plus a dict lookup replaces the whole loop.
    """
    memberships = Membership.objects.filter(
        organization__in=organizations, user=user, status=Membership.STATUS_ACTIVE
    ).select_related("role")
    return {membership.organization_id: membership for membership in memberships}


def list_members(organization: Organization) -> QuerySet[Membership]:
    return Membership.objects.for_organization(organization).select_related("user", "role")


def list_roles_for_organization(organization: Organization) -> QuerySet[Role]:
    """Every role selectable in ``organization``: the three global presets
    plus any custom roles that belong to it (PRD §4, custom roles are a
    per-project feature flag, off by default, but the data model doesn't
    change to support them — see ``roles.py``)."""
    return Role.objects.filter(Q(organization__isnull=True) | Q(organization=organization))


def list_invitations(organization: Organization) -> QuerySet[Invitation]:
    return Invitation.objects.for_organization(organization).select_related("role", "invited_by")


def get_invitation_by_token(token: str) -> Invitation | None:
    return Invitation.objects.select_related("organization", "role").filter(token=token).first()


def get_role(role_id: str | UUID) -> Role | None:
    return Role.objects.filter(pk=str(role_id)).first()


def get_membership_by_id(
    organization: Organization, membership_id: str | UUID
) -> Membership | None:
    return (
        Membership.objects.filter(organization=organization, pk=membership_id)
        .select_related("role")
        .first()
    )


def resolve_permission_codes(membership: Membership | None) -> list[str]:
    if membership is None:
        return []
    return sorted(membership.role.permissions)


def registered_permission_codes() -> list[str]:
    return [code for code, _guard in registry]
