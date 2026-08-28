"""``GET /api/v1/orgs/<org_slug>/audit/``."""

import pytest
from django.test import Client

from keel.accounts.models import User
from keel.audit.models import AuditLog
from keel.organizations import services
from keel.organizations.models import Membership, Role

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


def test_owner_can_list_the_organizations_audit_log() -> None:
    owner = _user("owner")
    # create_organization is itself @audited and records the row
    # inline rather than via a deferred on_commit callback that this
    # test's transactional wrapping would otherwise have silently
    # swallowed — so its own "organization.created" row is real and
    # expected here, alongside the two rows created directly below.
    org = services.create_organization(name="Acme", slug="acme", actor=owner)
    AuditLog.objects.create(organization=org, actor=owner, action="widget.created")
    AuditLog.objects.create(organization=org, actor=owner, action="widget.deleted")

    response = _client_for(owner).get(f"/api/v1/orgs/{org.slug}/audit/")

    assert response.status_code == 200
    body = response.json()
    assert "results" in body and "next" in body and "previous" in body
    assert len(body["results"]) == 3
    assert {row["action"] for row in body["results"]} == {
        "widget.created",
        "widget.deleted",
        "organization.created",
    }


def test_a_member_without_audit_view_is_denied() -> None:
    owner = _user("owner2")
    org = services.create_organization(name="Acme2", slug="acme2", actor=owner)
    no_permissions_role = Role.objects.create(name="No permissions", permissions=[])
    member = _user("member")
    Membership.objects.create(
        organization=org, user=member, role=no_permissions_role, status=Membership.STATUS_ACTIVE
    )

    response = _client_for(member).get(f"/api/v1/orgs/{org.slug}/audit/")

    assert response.status_code == 403


def test_rows_from_another_organization_are_not_visible() -> None:
    owner_a = _user("owner-a")
    org_a = services.create_organization(name="Acme A", slug="acme-a", actor=owner_a)
    owner_b = _user("owner-b")
    org_b = services.create_organization(name="Acme B", slug="acme-b", actor=owner_b)
    AuditLog.objects.create(organization=org_a, actor=owner_a, action="widget.created")
    AuditLog.objects.create(organization=org_b, actor=owner_b, action="widget.created")

    response = _client_for(owner_a).get(f"/api/v1/orgs/{org_a.slug}/audit/")

    assert response.status_code == 200
    body = response.json()
    # org_a's own "organization.created" row (recorded inline, see the
    # sibling test above) plus the "widget.created" row
    # created directly — org_b's rows must not appear in either count.
    assert len(body["results"]) == 2
    assert {row["action"] for row in body["results"]} == {
        "widget.created",
        "organization.created",
    }
