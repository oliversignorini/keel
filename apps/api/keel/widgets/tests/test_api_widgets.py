"""End-to-end API tests over the real URLconf (PRD §7 demo-resource route
table; docs/plans/phase-6.md 6.D acceptance: "Widget CRUD works end to
end with permission enforcement at every action").

Uses Django's plain test ``Client`` with ``force_login`` rather than
DRF's ``APIClient.force_authenticate`` — phase-10.md 10.B moved this
endpoint to Ninja, and ``force_authenticate`` only patches DRF's own
authentication pipeline, which a Ninja route never runs through.
``force_login`` sets the real Django session, which
``keel.core.ninja_auth.session_auth`` reads like any other request.
"""

import pytest
from django.test import Client

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


def test_owner_can_create_list_retrieve_update_and_delete_a_widget() -> None:
    org, owner = _org_with_owner()
    client = _client_for(owner)

    response = client.post(
        f"/api/v1/orgs/{org.slug}/widgets/",
        {"name": "Sprocket"},
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    widget_id = response.json()["id"]

    response = client.get(f"/api/v1/orgs/{org.slug}/widgets/")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["results"]] == [widget_id]

    response = client.get(f"/api/v1/orgs/{org.slug}/widgets/{widget_id}/")
    assert response.status_code == 200
    assert response.json()["name"] == "Sprocket"

    response = client.patch(
        f"/api/v1/orgs/{org.slug}/widgets/{widget_id}/",
        {"status": "archived"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == "archived"

    response = client.delete(f"/api/v1/orgs/{org.slug}/widgets/{widget_id}/")
    assert response.status_code == 204
    assert not Widget.objects.filter(pk=widget_id).exists()


def test_put_is_accepted_the_same_as_patch() -> None:
    """DRF's UpdateModelMixin registered both PUT and PATCH — stage
    10.D's route-by-route diff caught PUT's absence as a real gap, not
    just a docs mismatch, so it is tested directly here."""
    org, owner = _org_with_owner()
    client = _client_for(owner)
    response = client.post(
        f"/api/v1/orgs/{org.slug}/widgets/",
        {"name": "Sprocket"},
        content_type="application/json",
    )
    widget_id = response.json()["id"]

    response = client.put(
        f"/api/v1/orgs/{org.slug}/widgets/{widget_id}/",
        {"status": "archived"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "archived"


def test_widgets_view_only_member_cannot_create() -> None:
    org, _owner = _org_with_owner()
    member = _member_with_permissions(org, [Perm.WIDGETS_VIEW])
    client = _client_for(member)

    response = client.post(
        f"/api/v1/orgs/{org.slug}/widgets/",
        {"name": "Sprocket"},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


def test_widgets_view_only_member_can_list_and_retrieve() -> None:
    org, owner = _org_with_owner()
    member = _member_with_permissions(org, [Perm.WIDGETS_VIEW])
    owner_client = _client_for(owner)
    response = owner_client.post(
        f"/api/v1/orgs/{org.slug}/widgets/",
        {"name": "Sprocket"},
        content_type="application/json",
    )
    widget_id = response.json()["id"]

    member_client = _client_for(member)
    response = member_client.get(f"/api/v1/orgs/{org.slug}/widgets/")
    assert response.status_code == 200
    response = member_client.get(f"/api/v1/orgs/{org.slug}/widgets/{widget_id}/")
    assert response.status_code == 200


def test_member_with_no_permissions_gets_403_on_list() -> None:
    org, _owner = _org_with_owner()
    member = _member_with_permissions(org, [])
    client = _client_for(member)

    response = client.get(f"/api/v1/orgs/{org.slug}/widgets/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


def test_nonmember_gets_404_not_403_for_a_widget_in_another_org() -> None:
    org, owner = _org_with_owner()
    owner_client = _client_for(owner)
    response = owner_client.post(
        f"/api/v1/orgs/{org.slug}/widgets/",
        {"name": "Sprocket"},
        content_type="application/json",
    )
    widget_id = response.json()["id"]

    other_org, other_owner = _org_with_owner()
    other_client = _client_for(other_owner)

    response = other_client.get(f"/api/v1/orgs/{other_org.slug}/widgets/{widget_id}/")

    assert response.status_code == 404


def test_create_rejects_a_blank_name_with_400() -> None:
    org, owner = _org_with_owner()
    client = _client_for(owner)

    response = client.post(
        f"/api/v1/orgs/{org.slug}/widgets/",
        {"name": ""},
        content_type="application/json",
    )

    assert response.status_code == 400
    fields = {row["field"] for row in response.json()["error"]["details"]}
    assert "name" in fields
