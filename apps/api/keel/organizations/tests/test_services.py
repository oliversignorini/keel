"""Services (PRD §8 Phase 3 acceptance; phase-3.md B.1)."""

import pytest
from django.utils import timezone

from keel.accounts.models import User
from keel.billing.models import Plan, Price, Subscription
from keel.core.exceptions import (
    Conflict,
    PaymentRequired,
    PermissionDeniedWithReason,
    UnprocessableEntity,
)
from keel.organizations import services
from keel.organizations.models import Membership, Organization, Role
from keel.organizations.permissions import Perm
from keel.organizations.roles import PRESET_ADMIN, PRESET_MEMBER, PRESET_OWNER

pytestmark = pytest.mark.django_db


def _user(email: str = "creator@example.com") -> User:
    return User.objects.create_user(email=email, password="s3cret-pass")


def test_create_organization_is_atomic_org_owner_membership_and_three_preset_roles() -> None:
    creator = _user()

    org = services.create_organization(name="Acme", slug="acme", created_by=creator)

    assert Organization.objects.filter(pk=org.pk).exists()
    membership = Membership.objects.get(organization=org, user=creator)
    assert membership.role.name == PRESET_OWNER
    assert membership.status == Membership.STATUS_ACTIVE
    preset_names = set(
        Role.objects.filter(organization=None, is_preset=True).values_list("name", flat=True)
    )
    assert preset_names == {PRESET_OWNER, PRESET_ADMIN, PRESET_MEMBER}
    assert Perm.ORG_TRANSFER in membership.role.permissions


def test_create_organization_fails_atomically_on_duplicate_slug() -> None:
    creator = _user()
    services.create_organization(name="Acme", slug="acme", created_by=creator)

    with pytest.raises(Exception):  # noqa: B017 - IntegrityError from the unique slug constraint
        services.create_organization(name="Acme Two", slug="acme", created_by=creator)

    # No stray membership/org left behind by the failed attempt.
    assert Organization.objects.filter(slug="acme").count() == 1
    assert Membership.objects.filter(user=creator).count() == 1


_org_counter = 0


def _sole_owner_org() -> tuple[Organization, Membership]:
    global _org_counter
    _org_counter += 1
    creator = _user(f"owner-{_org_counter}@example.com")
    org = services.create_organization(name="Acme", slug=f"acme-{_org_counter}", created_by=creator)
    membership = Membership.objects.get(organization=org, user=creator)
    return org, membership


def test_remove_member_denies_removing_the_last_owner() -> None:
    _org, owner_membership = _sole_owner_org()

    with pytest.raises(PermissionDeniedWithReason) as exc_info:
        services.remove_member(membership=owner_membership, actor=owner_membership.user)

    assert exc_info.value.code == "cannot_remove_last_owner"
    assert Membership.objects.filter(pk=owner_membership.pk).exists()


def test_remove_member_succeeds_when_not_the_last_owner() -> None:
    org, owner_membership = _sole_owner_org()
    second_owner = _user("second-owner@example.com")
    second_membership = Membership.objects.create(
        organization=org,
        user=second_owner,
        role=owner_membership.role,
        status=Membership.STATUS_ACTIVE,
    )

    services.remove_member(membership=owner_membership, actor=second_owner)

    assert not Membership.objects.filter(pk=owner_membership.pk).exists()
    assert Membership.objects.filter(pk=second_membership.pk).exists()


def test_change_member_role_denies_demoting_the_last_owner() -> None:
    _org, owner_membership = _sole_owner_org()
    member_role = Role.objects.get(organization=None, name=PRESET_MEMBER)

    with pytest.raises(Conflict) as exc_info:
        services.change_member_role(
            membership=owner_membership, role=member_role, actor=owner_membership.user
        )

    assert exc_info.value.code == "cannot_demote_last_owner"
    owner_membership.refresh_from_db()
    assert Perm.ORG_TRANSFER in owner_membership.role.permissions


def test_change_member_role_allows_demoting_an_owner_when_another_owner_remains() -> None:
    org, owner_membership = _sole_owner_org()
    second_owner = _user("second-owner@example.com")
    Membership.objects.create(
        organization=org,
        user=second_owner,
        role=owner_membership.role,
        status=Membership.STATUS_ACTIVE,
    )
    member_role = Role.objects.get(organization=None, name=PRESET_MEMBER)

    services.change_member_role(membership=owner_membership, role=member_role, actor=second_owner)

    owner_membership.refresh_from_db()
    assert owner_membership.role_id == member_role.id


def test_transfer_ownership_swaps_roles() -> None:
    org, owner_membership = _sole_owner_org()
    new_owner = _user("new-owner@example.com")
    admin_role = Role.objects.get(organization=None, name=PRESET_ADMIN)
    new_owner_membership = Membership.objects.create(
        organization=org, user=new_owner, role=admin_role, status=Membership.STATUS_ACTIVE
    )

    services.transfer_ownership(
        organization=org,
        from_membership=owner_membership,
        to_membership=new_owner_membership,
        actor=owner_membership.user,
    )

    owner_membership.refresh_from_db()
    new_owner_membership.refresh_from_db()
    assert new_owner_membership.role.name == PRESET_OWNER
    assert owner_membership.role.name == PRESET_ADMIN


def test_transfer_ownership_rejects_a_membership_from_another_organization() -> None:
    org, owner_membership = _sole_owner_org()
    _other_org, other_membership = _sole_owner_org()

    with pytest.raises(UnprocessableEntity):
        services.transfer_ownership(
            organization=org,
            from_membership=owner_membership,
            to_membership=other_membership,
            actor=owner_membership.user,
        )


def test_invitation_lifecycle_create_revoke_accept() -> None:
    org, owner_membership = _sole_owner_org()
    member_role = Role.objects.get(organization=None, name=PRESET_MEMBER)

    invitation = services.create_invitation(
        organization=org,
        email="Invitee@Example.com",
        role=member_role,
        invited_by=owner_membership.user,
    )
    assert invitation.email == "invitee@example.com"
    assert invitation.expires_at > timezone.now()
    assert invitation.token

    invitee = _user("invitee@example.com")
    membership = services.accept_invitation(invitation=invitation, user=invitee)

    invitation.refresh_from_db()
    assert invitation.accepted_at is not None
    assert membership.organization_id == org.id
    assert membership.role_id == member_role.id
    assert membership.status == Membership.STATUS_ACTIVE


def test_revoke_invitation_sets_revoked_at() -> None:
    org, owner_membership = _sole_owner_org()
    member_role = Role.objects.get(organization=None, name=PRESET_MEMBER)
    invitation = services.create_invitation(
        organization=org,
        email="invitee@example.com",
        role=member_role,
        invited_by=owner_membership.user,
    )

    services.revoke_invitation(invitation=invitation, actor=owner_membership.user)

    invitation.refresh_from_db()
    assert invitation.revoked_at is not None


def _subscribe_to_plan_with_seat_limit(org: Organization, seats: int) -> None:
    plan = Plan.objects.create(
        code=f"seat-limited-{org.pk}",
        name="Seat limited",
        entitlements={"limits": {"seats": seats}},
    )
    price = Price.objects.create(
        plan=plan,
        stripe_price_id=f"price-{org.pk}",
        interval=Price.INTERVAL_MONTH,
        unit_amount=1900,
        currency="AUD",
    )
    Subscription.objects.create(
        organization=org,
        stripe_subscription_id=f"sub-{org.pk}",
        plan=plan,
        price=price,
        status="active",
    )


def test_accept_invitation_denies_beyond_the_seat_entitlement() -> None:
    """docs/plans/phase-4.md B.4 acceptance: adding a member beyond the
    seat entitlement returns 402 with upgrade context."""
    org, owner_membership = _sole_owner_org()
    _subscribe_to_plan_with_seat_limit(org, seats=1)  # the owner already fills the one seat
    member_role = Role.objects.get(organization=None, name=PRESET_MEMBER)
    invitation = services.create_invitation(
        organization=org,
        email="invitee@example.com",
        role=member_role,
        invited_by=owner_membership.user,
    )
    invitee = _user("invitee@example.com")

    with pytest.raises(PaymentRequired) as exc_info:
        services.accept_invitation(invitation=invitation, user=invitee)

    assert exc_info.value.code == "limit_exceeded"
    assert exc_info.value.details == {"resource": "seats", "limit": 1, "current_usage": 1}
    invitation.refresh_from_db()
    assert invitation.accepted_at is None, "a denied acceptance must change nothing"
    assert not Membership.objects.filter(organization=org, user=invitee).exists()


def test_accept_invitation_reactivating_a_suspended_membership_is_checked_as_a_new_seat() -> None:
    """A suspended membership isn't counted by the "seats" resource
    counter (it filters on STATUS_ACTIVE), so reactivating one genuinely
    raises active usage by one and must be checked like any other new
    seat."""
    org, owner_membership = _sole_owner_org()
    member_role = Role.objects.get(organization=None, name=PRESET_MEMBER)
    invitee = _user("invitee@example.com")
    Membership.objects.create(
        organization=org, user=invitee, role=member_role, status=Membership.STATUS_SUSPENDED
    )
    _subscribe_to_plan_with_seat_limit(org, seats=1)  # owner alone already fills the one seat
    invitation = services.create_invitation(
        organization=org,
        email="invitee@example.com",
        role=member_role,
        invited_by=owner_membership.user,
    )

    with pytest.raises(PaymentRequired):
        services.accept_invitation(invitation=invitation, user=invitee)

    assert Membership.objects.get(organization=org, user=invitee).status == (
        Membership.STATUS_SUSPENDED
    )


def test_accept_invitation_re_accepting_an_already_active_membership_is_not_rechecked() -> None:
    """Re-accepting an invitation for a membership that's already active
    is a pure no-op and must not be blocked even when the org is
    otherwise at its seat cap."""
    org, owner_membership = _sole_owner_org()
    member_role = Role.objects.get(organization=None, name=PRESET_MEMBER)
    invitee = _user("invitee@example.com")
    Membership.objects.create(
        organization=org, user=invitee, role=member_role, status=Membership.STATUS_ACTIVE
    )
    _subscribe_to_plan_with_seat_limit(org, seats=2)  # owner + invitee already fill both seats
    invitation = services.create_invitation(
        organization=org,
        email="invitee@example.com",
        role=member_role,
        invited_by=owner_membership.user,
    )

    membership = services.accept_invitation(invitation=invitation, user=invitee)

    assert membership.status == Membership.STATUS_ACTIVE


def test_accept_invitation_reactivates_a_suspended_membership() -> None:
    org, owner_membership = _sole_owner_org()
    member_role = Role.objects.get(organization=None, name=PRESET_MEMBER)
    admin_role = Role.objects.get(organization=None, name=PRESET_ADMIN)
    invitee = _user("invitee@example.com")
    Membership.objects.create(
        organization=org, user=invitee, role=admin_role, status=Membership.STATUS_SUSPENDED
    )
    invitation = services.create_invitation(
        organization=org,
        email="invitee@example.com",
        role=member_role,
        invited_by=owner_membership.user,
    )

    membership = services.accept_invitation(invitation=invitation, user=invitee)

    assert membership.status == Membership.STATUS_ACTIVE
    assert membership.role_id == member_role.id
