"""Django admin's "Impersonate" action (PRD §6 "Impersonation")."""

from typing import Any

import pytest
from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponseRedirect
from django.test import RequestFactory

from keel.accounts.admin import UserAdmin
from keel.accounts.models import User
from keel.audit.models import AuditLog
from keel.core.impersonation import IMPERSONATOR_SESSION_KEY

pytestmark = pytest.mark.django_db


def _staff_request(staff: User) -> Any:
    request = RequestFactory().post("/admin/accounts/user/")
    request.session = SessionStore()
    request.session.create()
    request.user = staff
    request._messages = FallbackStorage(request)  # type: ignore[attr-defined]
    return request


def test_impersonate_starts_the_session_and_writes_an_audit_row() -> None:
    staff = User.objects.create_user(email="staff@example.com", password="x", is_staff=True)
    target = User.objects.create_user(email="target@example.com", password="x")
    request = _staff_request(staff)
    admin_instance = UserAdmin(User, AdminSite())

    response = admin_instance.impersonate(request, User.objects.filter(pk=target.pk))

    assert isinstance(response, HttpResponseRedirect)
    assert response.status_code == 302
    assert response.url == settings.APP_FRONTEND_URL
    assert request.session[IMPERSONATOR_SESSION_KEY] == str(staff.pk)
    assert request.user == target  # django.contrib.auth.login rebinds request.user

    row = AuditLog.objects.get(action="impersonation.start")
    assert row.actor_id == target.pk
    assert row.impersonator_id == staff.pk
    # Written through keel.core.audit's recorder seam
    # (keel.audit.services.record_impersonation_start), not by the admin
    # action — the target fields are the recorder's.
    assert row.target_type == "User"
    assert row.target_id == str(target.pk)


def test_impersonate_refuses_more_than_one_selected_user() -> None:
    staff = User.objects.create_user(email="staff2@example.com", password="x", is_staff=True)
    target_a = User.objects.create_user(email="a@example.com", password="x")
    target_b = User.objects.create_user(email="b@example.com", password="x")
    request = _staff_request(staff)
    admin_instance = UserAdmin(User, AdminSite())

    response = admin_instance.impersonate(
        request, User.objects.filter(pk__in=[target_a.pk, target_b.pk])
    )

    assert response is None
    assert not AuditLog.objects.filter(action="impersonation.start").exists()


def test_impersonate_refuses_impersonating_self() -> None:
    staff = User.objects.create_user(email="staff3@example.com", password="x", is_staff=True)
    request = _staff_request(staff)
    admin_instance = UserAdmin(User, AdminSite())

    response = admin_instance.impersonate(request, User.objects.filter(pk=staff.pk))

    assert response is None
    assert not AuditLog.objects.filter(action="impersonation.start").exists()
