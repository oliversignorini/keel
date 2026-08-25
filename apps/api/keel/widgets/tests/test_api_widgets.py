"""End-to-end API tests over the real URLconf (PRD §7 demo-resource route
table; docs/plans/phase-6.md 6.D acceptance: "Widget CRUD works end to
end with permission enforcement at every action")."""

import pytest
from rest_framework.test import APIClient

from keel.accounts.models import User
from keel.organizations import services as org_services
from keel.organizations.models import Role
from keel.organizations.permissions import Perm
from keel.widgets.models import Widget

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


def test_owner_can_create_list_retrieve_update_and_delete_a_widget() -> None:
    org, owner = _org_with_owner()
    client = _client_for(owner)

    response = client.post(f"/api/v1/organizations/{org.slug}/widgets/", {"name": "Sprocket"})
    assert response.status_code == 201, response.data
    widget_id = response.data["id"]

    response = client.get(f"/api/v1/organizations/{org.slug}/widgets/")
    assert response.status_code == 200
    assert [row["id"] for row in response.data["results"]] == [widget_id]

    response = client.get(f"/api/v1/organizations/{org.slug}/widgets/{widget_id}/")
    assert response.status_code == 200
    assert response.data["name"] == "Sprocket"

    response = client.patch(
        f"/api/v1/organizations/{org.slug}/widgets/{widget_id}/", {"status": "archived"}
    )
    assert response.status_code == 200
    assert response.data["status"] == "archived"

    response = client.delete(f"/api/v1/organizations/{org.slug}/widgets/{widget_id}/")
    assert response.status_code == 204
    assert not Widget.objects.filter(pk=widget_id).exists()


def test_widgets_view_only_member_cannot_create() -> None:
    org, _owner = _org_with_owner()
    member = _member_with_permissions(org, [Perm.WIDGETS_VIEW])
    client = _client_for(member)

    response = client.post(f"/api/v1/organizations/{org.slug}/widgets/", {"name": "Sprocket"})

    assert response.status_code == 403
    assert response.data["error"]["code"] == "insufficient_role"


def test_widgets_view_only_member_can_list_and_retrieve() -> None:
    org, owner = _org_with_owner()
    member = _member_with_permissions(org, [Perm.WIDGETS_VIEW])
    owner_client = _client_for(owner)
    response = owner_client.post(f"/api/v1/organizations/{org.slug}/widgets/", {"name": "Sprocket"})
    widget_id = response.data["id"]

    member_client = _client_for(member)
    response = member_client.get(f"/api/v1/organizations/{org.slug}/widgets/")
    assert response.status_code == 200
    response = member_client.get(f"/api/v1/organizations/{org.slug}/widgets/{widget_id}/")
    assert response.status_code == 200


def test_member_with_no_permissions_gets_403_on_list() -> None:
    org, _owner = _org_with_owner()
    member = _member_with_permissions(org, [])
    client = _client_for(member)

    response = client.get(f"/api/v1/organizations/{org.slug}/widgets/")

    assert response.status_code == 403
    assert response.data["error"]["code"] == "insufficient_role"


def test_nonmember_gets_404_not_403_for_a_widget_in_another_org() -> None:
    org, owner = _org_with_owner()
    owner_client = _client_for(owner)
    response = owner_client.post(f"/api/v1/organizations/{org.slug}/widgets/", {"name": "Sprocket"})
    widget_id = response.data["id"]

    other_org, other_owner = _org_with_owner()
    other_client = _client_for(other_owner)

    response = other_client.get(f"/api/v1/organizations/{other_org.slug}/widgets/{widget_id}/")

    assert response.status_code == 404


def test_create_rejects_a_blank_name_with_400() -> None:
    org, owner = _org_with_owner()
    client = _client_for(owner)

    response = client.post(f"/api/v1/organizations/{org.slug}/widgets/", {"name": ""})

    assert response.status_code == 400
    fields = {row["field"] for row in response.data["error"]["details"]}
    assert "name" in fields
