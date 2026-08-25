"""``POST /api/v1/impersonation/exit/`` (PRD §6 "Impersonation";
docs/plans/phase-8.md 8.3)."""

import pytest
from rest_framework.test import APIClient

from keel.accounts.models import User
from keel.audit.models import AuditLog
from keel.core.impersonation import IMPERSONATOR_SESSION_KEY

pytestmark = pytest.mark.django_db


def test_exit_restores_the_staff_session_and_writes_an_audit_row() -> None:
    staff = User.objects.create_user(
        email="staff@example.com", password="s3cret-pass", is_staff=True
    )
    target = User.objects.create_user(email="target@example.com", password="s3cret-pass")
    client = APIClient()
    client.force_login(target)
    session = client.session
    session[IMPERSONATOR_SESSION_KEY] = str(staff.pk)
    session.save()

    response = client.post("/api/v1/impersonation/exit/")

    assert response.status_code == 204
    assert IMPERSONATOR_SESSION_KEY not in client.session
    row = AuditLog.objects.get(action="impersonation.end")
    assert row.actor_id == target.pk
    assert row.impersonator_id == staff.pk


def test_exit_404s_when_not_impersonating() -> None:
    user = User.objects.create_user(email="user@example.com", password="s3cret-pass")
    client = APIClient()
    client.force_login(user)

    response = client.post("/api/v1/impersonation/exit/")

    assert response.status_code == 404
