"""Row factories used both by production viewsets' ``test_factory`` dotted
paths (PRD §4 invariant 7 — the cross-org meta-test walk) and directly by
this app's own tests."""

from datetime import timedelta

from django.utils import timezone
from django.utils.crypto import get_random_string

from keel.accounts.models import User
from keel.organizations.models import Invitation, Membership, Organization, Role
from keel.organizations.permissions import Perm
from keel.organizations.roles import PRESET_MEMBER, seed_preset_roles


def _unique_user(organization: Organization, tag: str) -> User:
    return User.objects.create_user(
        email=f"{tag}-{organization.pk}-{get_random_string(6).lower()}@example.com",
        password="s3cret-pass",
    )


def membership_factory(organization: Organization) -> Membership:
    role = seed_preset_roles()[PRESET_MEMBER]
    return Membership.objects.create(
        organization=organization,
        user=_unique_user(organization, "member"),
        role=role,
        status=Membership.STATUS_ACTIVE,
    )


def role_factory(organization: Organization) -> Role:
    return Role.objects.create(
        organization=organization,
        name=f"Custom role {get_random_string(6)}",
        permissions=[Perm.MEMBERS_VIEW],
    )


def invitation_factory(organization: Organization) -> Invitation:
    role = seed_preset_roles()[PRESET_MEMBER]
    inviter = _unique_user(organization, "inviter")
    return Invitation.objects.create(
        organization=organization,
        email=f"invitee-{get_random_string(6).lower()}@example.com",
        role=role,
        invited_by=inviter,
        token=get_random_string(48),
        expires_at=timezone.now() + timedelta(days=7),
    )
