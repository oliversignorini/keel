"""End-to-end API tests over the real URLconf (PRD §7; §8 Phase 3
acceptance): organisations, members, roles, invitations, /me,
/permissions, and the invitation-accept edge cases (phase-3.md B.4).
"""

import pytest
from rest_framework.test import APIClient

from keel.accounts.models import User
from keel.organizations import services
from keel.organizations.models import Invitation, Membership, Role
from keel.organizations.permissions import Perm
from keel.organizations.roles import PRESET_ADMIN, PRESET_MEMBER, PRESET_OWNER

pytestmark = pytest.mark.django_db

_counter = 0


def _user(prefix: str = "user") -> User:
    global _counter
    _counter += 1
    return User.objects.create_user(
        email=f"{prefix}-{_counter}@example.com", password="s3cret-pass"
    )


def _client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _org_with_owner():
    global _counter
    _counter += 1
    creator = _user("owner")
    org = services.create_organization(name="Acme", slug=f"acme-{_counter}", created_by=creator)
    return org, creator


def test_create_and_list_organizations() -> None:
    creator = _user()
    client = _client_for(creator)

    response = client.post("/api/v1/organizations/", {"name": "Acme", "slug": "acme-co"})
    assert response.status_code == 201, response.data
    assert response.data["slug"] == "acme-co"

    response = client.get("/api/v1/organizations/")
    assert response.status_code == 200
    slugs = [row["slug"] for row in response.data["results"]]
    assert "acme-co" in slugs


def test_organization_detail_404s_for_nonmember_and_nonexistent_slug() -> None:
    org, _creator = _org_with_owner()
    outsider = _user("outsider")
    client = _client_for(outsider)

    real_response = client.get(f"/api/v1/organizations/{org.slug}/")
    fake_response = client.get("/api/v1/organizations/does-not-exist/")

    assert real_response.status_code == 404
    assert fake_response.status_code == 404


def test_member_view_403_denial_carries_reason_as_code() -> None:
    org, _creator = _org_with_owner()
    no_perms_role = Role.objects.create(name="No perms", permissions=[])
    powerless = _user("powerless")
    Membership.objects.create(
        organization=org, user=powerless, role=no_perms_role, status=Membership.STATUS_ACTIVE
    )
    client = _client_for(powerless)

    response = client.get(f"/api/v1/organizations/{org.slug}/members/")

    assert response.status_code == 403
    assert response.data["error"]["code"] == "insufficient_role"


def test_last_owner_cannot_be_removed_via_api() -> None:
    org, creator = _org_with_owner()
    owner_membership = Membership.objects.get(organization=org, user=creator)
    client = _client_for(creator)

    response = client.delete(f"/api/v1/organizations/{org.slug}/members/{owner_membership.pk}/")

    assert response.status_code == 403
    assert response.data["error"]["code"] == "cannot_remove_last_owner"
    assert Membership.objects.filter(pk=owner_membership.pk).exists()


def test_last_owner_cannot_be_demoted_via_api() -> None:
    org, creator = _org_with_owner()
    owner_membership = Membership.objects.get(organization=org, user=creator)
    member_role = Role.objects.get(organization=None, name=PRESET_MEMBER)
    client = _client_for(creator)

    response = client.patch(
        f"/api/v1/organizations/{org.slug}/members/{owner_membership.pk}/",
        {"role_id": str(member_role.pk)},
    )

    assert response.status_code == 409
    assert response.data["error"]["code"] == "cannot_demote_last_owner"


def test_invite_list_and_role_endpoints_return_expected_shapes() -> None:
    org, creator = _org_with_owner()
    member_role = Role.objects.get(organization=None, name=PRESET_MEMBER)
    client = _client_for(creator)

    invite_response = client.post(
        f"/api/v1/organizations/{org.slug}/invitations/",
        {"email": "invitee@example.com", "role_id": str(member_role.pk)},
    )
    assert invite_response.status_code == 201, invite_response.data
    assert invite_response.data["status"] == "pending"

    roles_response = client.get(f"/api/v1/organizations/{org.slug}/roles/")
    assert roles_response.status_code == 200
    role_names = {row["name"] for row in roles_response.data["results"]}
    assert {PRESET_OWNER, PRESET_ADMIN, PRESET_MEMBER} <= role_names


def test_permissions_registry_lists_registered_codes() -> None:
    client = _client_for(_user())

    response = client.get("/api/v1/permissions/")

    assert response.status_code == 200
    assert Perm.MEMBERS_VIEW in response.data["codes"]


def test_me_returns_organizations_role_and_permissions() -> None:
    org, creator = _org_with_owner()
    client = _client_for(creator)

    response = client.get("/api/v1/me/")

    assert response.status_code == 200
    assert response.data["user"]["email"] == creator.email
    org_row = next(row for row in response.data["organizations"] if row["slug"] == org.slug)
    assert org_row["role"] == PRESET_OWNER
    assert Perm.ORG_TRANSFER in org_row["permissions"]


# --- Invitation accept: the four edge cases (phase-3.md B.4) --------------


def _pending_invitation(org, creator, email: str = "invitee@example.com") -> Invitation:
    member_role = Role.objects.get(organization=None, name=PRESET_MEMBER)
    return services.create_invitation(
        organization=org, email=email, role=member_role, invited_by=creator
    )


def test_invite_wrong_email_is_rejected_without_disclosing_the_invitee() -> None:
    org, creator = _org_with_owner()
    invitation = _pending_invitation(org, creator, email="actual-invitee@example.com")
    wrong_person = _user("wrong")
    client = _client_for(wrong_person)

    response = client.post(f"/api/v1/invite/{invitation.token}/")

    assert response.status_code == 409
    assert response.data["error"]["code"] == "invalid_or_expired"
    assert "actual-invitee" not in str(response.data)


def test_expired_and_revoked_invitations_are_indistinguishable() -> None:
    from django.utils import timezone

    org, creator = _org_with_owner()
    expired = _pending_invitation(org, creator, email="expired@example.com")
    expired.expires_at = timezone.now() - timezone.timedelta(days=1)
    expired.save(update_fields=["expires_at"])
    revoked = _pending_invitation(org, creator, email="revoked@example.com")
    services.revoke_invitation(invitation=revoked, actor=creator)

    expired_user = User.objects.create_user(email="expired@example.com", password="s3cret-pass")
    revoked_user = User.objects.create_user(email="revoked@example.com", password="s3cret-pass")

    expired_response = _client_for(expired_user).post(f"/api/v1/invite/{expired.token}/")
    revoked_response = _client_for(revoked_user).post(f"/api/v1/invite/{revoked.token}/")

    assert expired_response.status_code == revoked_response.status_code == 409
    assert (
        expired_response.data["error"]["code"]
        == revoked_response.data["error"]["code"]
        == "invalid_or_expired"
    )


def test_invite_get_before_signup_flags_signup_required() -> None:
    org, creator = _org_with_owner()
    invitation = _pending_invitation(org, creator)

    response = APIClient().get(f"/api/v1/invite/{invitation.token}/")

    assert response.status_code == 200
    assert response.data["requires_signup"] is True
    assert response.data["email"] == invitation.email


def test_invite_accept_signed_in_matching_email() -> None:
    org, creator = _org_with_owner()
    invitation = _pending_invitation(org, creator, email="invitee@example.com")
    invitee = User.objects.create_user(email="invitee@example.com", password="s3cret-pass")
    client = _client_for(invitee)

    response = client.post(f"/api/v1/invite/{invitation.token}/")

    assert response.status_code == 200
    assert Membership.objects.filter(organization=org, user=invitee).exists()
