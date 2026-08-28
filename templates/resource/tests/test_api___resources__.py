"""End-to-end API tests over the real URLconf — CRUD plus permission
enforcement at every action, and the 404-not-403 cross-tenant answer
CLAUDE.md invariant 6 requires.

Uses Django's plain test ``Client`` with ``force_login``: Ninja routes
authenticate through ``keel.core.auth.session_auth``, which reads the real
Django session, so there is no framework-specific "force authenticate"
helper to reach for.
"""

import pytest
from django.test import Client

from keel.__app__.models import __Resource__
from keel.__app__.views import _VIEW
from keel.accounts.models import User
from keel.organizations import services as org_services
from keel.organizations.models import Role

pytestmark = pytest.mark.django_db

# keel:insert api_create_body

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
    org = org_services.create_organization(name="Acme", slug=f"acme-{_counter}", actor=creator)
    return org, creator


def _member_with_permissions(org, codes):
    from keel.organizations.models import Membership

    role = Role.objects.create(name=f"role-{codes}", permissions=list(codes))
    user = _user("member")
    Membership.objects.create(
        organization=org, user=user, role=role, status=Membership.STATUS_ACTIVE
    )
    return user


def test_owner_can_create_list_retrieve_update_and_delete() -> None:
    org, owner = _org_with_owner()
    client = _client_for(owner)

    response = client.post(
        f"/api/v1/orgs/{org.slug}/__resources__/",
        _CREATE_BODY,
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    row_id = response.json()["id"]

    response = client.get(f"/api/v1/orgs/{org.slug}/__resources__/")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["results"]] == [row_id]

    response = client.get(f"/api/v1/orgs/{org.slug}/__resources__/{row_id}/")
    assert response.status_code == 200
    # keel:insert api_retrieve_assertions

    # keel:insert api_patch_assertions

    response = client.delete(f"/api/v1/orgs/{org.slug}/__resources__/{row_id}/")
    assert response.status_code == 204
    assert not __Resource__.objects.filter(pk=row_id).exists()


def test_put_is_not_registered_only_patch_is() -> None:
    """PUT and PATCH sharing one operationId makes PATCH unreachable from
    the generated client, and a partial-update handler under PUT would
    misrepresent PUT's idempotent-by-substitution semantics. The route is
    PATCH-only — PUT gets Ninja's normal method-not-allowed response, not
    a silent partial update."""
    org, owner = _org_with_owner()
    client = _client_for(owner)
    response = client.post(
        f"/api/v1/orgs/{org.slug}/__resources__/",
        _CREATE_BODY,
        content_type="application/json",
    )
    row_id = response.json()["id"]

    response = client.put(
        f"/api/v1/orgs/{org.slug}/__resources__/{row_id}/",
        _CREATE_BODY,
        content_type="application/json",
    )

    assert response.status_code == 405


def test_view_only_member_cannot_create() -> None:
    org, _owner = _org_with_owner()
    member = _member_with_permissions(org, [_VIEW])
    client = _client_for(member)

    response = client.post(
        f"/api/v1/orgs/{org.slug}/__resources__/",
        _CREATE_BODY,
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


def test_view_only_member_can_list_and_retrieve() -> None:
    org, owner = _org_with_owner()
    member = _member_with_permissions(org, [_VIEW])
    owner_client = _client_for(owner)
    response = owner_client.post(
        f"/api/v1/orgs/{org.slug}/__resources__/",
        _CREATE_BODY,
        content_type="application/json",
    )
    row_id = response.json()["id"]

    member_client = _client_for(member)
    response = member_client.get(f"/api/v1/orgs/{org.slug}/__resources__/")
    assert response.status_code == 200
    response = member_client.get(f"/api/v1/orgs/{org.slug}/__resources__/{row_id}/")
    assert response.status_code == 200


def test_member_with_no_permissions_gets_403_on_list() -> None:
    org, _owner = _org_with_owner()
    member = _member_with_permissions(org, [])
    client = _client_for(member)

    response = client.get(f"/api/v1/orgs/{org.slug}/__resources__/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


def test_nonmember_gets_404_not_403_for_a_row_in_another_org() -> None:
    """404, never 403 — a 403 would confirm the row exists to someone
    outside the organisation that owns it (CLAUDE.md invariant 6)."""
    org, owner = _org_with_owner()
    owner_client = _client_for(owner)
    response = owner_client.post(
        f"/api/v1/orgs/{org.slug}/__resources__/",
        _CREATE_BODY,
        content_type="application/json",
    )
    row_id = response.json()["id"]

    other_org, other_owner = _org_with_owner()
    other_client = _client_for(other_owner)

    response = other_client.get(f"/api/v1/orgs/{other_org.slug}/__resources__/{row_id}/")

    assert response.status_code == 404


# keel:insert api_validation_test
