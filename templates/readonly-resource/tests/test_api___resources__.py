"""End-to-end API tests over the real URLconf, read-only edition: list,
retrieve, permission enforcement on both, the 404-not-403 cross-tenant
answer CLAUDE.md invariant 6 requires, and — the test that matters most
here — that the write methods are genuinely absent rather than merely
undocumented.
"""

import pytest
from django.test import Client

from keel.__app__.tests.factories import __resource___factory
from keel.__app__.views import _VIEW
from keel.accounts.models import User
from keel.organizations import services as org_services
from keel.organizations.models import Role

pytestmark = pytest.mark.django_db

_counter = 0


def _user(prefix: str = "user") -> User:
    global _counter
    _counter += 1
    return User.objects.create_user(
        email=f"{prefix}-{_counter}@example.com", password="s3cret-pass"
    )


def _client_for(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _org_with_owner():
    global _counter
    _counter += 1
    creator = _user("owner")
    org = org_services.create_organization(name="Acme", slug=f"acme-{_counter}", created_by=creator)
    return org, creator


def _member_with_permissions(org, codes):
    from keel.organizations.models import Membership

    role = Role.objects.create(name=f"role-{codes}", permissions=list(codes))
    user = _user("member")
    Membership.objects.create(
        organization=org, user=user, role=role, status=Membership.STATUS_ACTIVE
    )
    return user


def test_member_can_list_and_retrieve() -> None:
    org, owner = _org_with_owner()
    row = __resource___factory(org)
    client = _client_for(owner)

    response = client.get(f"/api/v1/orgs/{org.slug}/__resources__/")
    assert response.status_code == 200
    assert [r["id"] for r in response.json()["results"]] == [str(row.id)]

    response = client.get(f"/api/v1/orgs/{org.slug}/__resources__/{row.id}/")
    assert response.status_code == 200


def test_write_methods_are_not_registered() -> None:
    """No POST, PATCH or DELETE route exists. Asserted rather than assumed
    because a read-only resource that quietly grows a write path is a
    write path with no audit decorator and no permission code behind it."""
    org, owner = _org_with_owner()
    row = __resource___factory(org)
    client = _client_for(owner)

    assert client.post(f"/api/v1/orgs/{org.slug}/__resources__/", {}).status_code == 405
    assert client.patch(f"/api/v1/orgs/{org.slug}/__resources__/{row.id}/", {}).status_code == 405
    assert client.delete(f"/api/v1/orgs/{org.slug}/__resources__/{row.id}/").status_code == 405


def test_member_with_no_permissions_gets_403_on_list() -> None:
    org, _owner = _org_with_owner()
    member = _member_with_permissions(org, [])
    client = _client_for(member)

    response = client.get(f"/api/v1/orgs/{org.slug}/__resources__/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


def test_view_member_can_list() -> None:
    org, _owner = _org_with_owner()
    __resource___factory(org)
    member = _member_with_permissions(org, [_VIEW])
    client = _client_for(member)

    assert client.get(f"/api/v1/orgs/{org.slug}/__resources__/").status_code == 200


def test_nonmember_gets_404_not_403_for_a_row_in_another_org() -> None:
    """404, never 403 — a 403 would confirm the row exists to someone
    outside the organisation that owns it (CLAUDE.md invariant 6)."""
    org, _owner = _org_with_owner()
    row = __resource___factory(org)

    other_org, other_owner = _org_with_owner()
    other_client = _client_for(other_owner)

    response = other_client.get(f"/api/v1/orgs/{other_org.slug}/__resources__/{row.id}/")

    assert response.status_code == 404
