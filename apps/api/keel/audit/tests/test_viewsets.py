"""``GET /api/v1/organizations/<org_slug>/audit/`` (PRD §7; docs/plans/
phase-8.md 8.2)."""

import pytest
from rest_framework.test import APIClient

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


def _client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_owner_can_list_the_organizations_audit_log() -> None:
    owner = _user("owner")
    org = services.create_organization(name="Acme", slug="acme", created_by=owner)
    AuditLog.objects.create(organization=org, actor=owner, action="widget.created")
    AuditLog.objects.create(organization=org, actor=owner, action="widget.deleted")

    response = _client_for(owner).get(f"/api/v1/organizations/{org.slug}/audit/")

    assert response.status_code == 200
    body = response.json()
    assert "results" in body and "next" in body and "previous" in body
    assert len(body["results"]) == 2
    assert {row["action"] for row in body["results"]} == {"widget.created", "widget.deleted"}


def test_a_member_without_audit_view_is_denied() -> None:
    owner = _user("owner2")
    org = services.create_organization(name="Acme2", slug="acme2", created_by=owner)
    no_permissions_role = Role.objects.create(name="No permissions", permissions=[])
    member = _user("member")
    Membership.objects.create(
        organization=org, user=member, role=no_permissions_role, status=Membership.STATUS_ACTIVE
    )

    response = _client_for(member).get(f"/api/v1/organizations/{org.slug}/audit/")

    assert response.status_code == 403


def test_rows_from_another_organization_are_not_visible() -> None:
    owner_a = _user("owner-a")
    org_a = services.create_organization(name="Acme A", slug="acme-a", created_by=owner_a)
    owner_b = _user("owner-b")
    org_b = services.create_organization(name="Acme B", slug="acme-b", created_by=owner_b)
    AuditLog.objects.create(organization=org_a, actor=owner_a, action="widget.created")
    AuditLog.objects.create(organization=org_b, actor=owner_b, action="widget.created")

    response = _client_for(owner_a).get(f"/api/v1/organizations/{org_a.slug}/audit/")

    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
