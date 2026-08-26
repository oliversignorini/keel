"""The four impersonation restrictions (PRD §6 "Impersonation";
docs/plans/phase-8.md 8.3), each tested by calling the service directly
with an impersonated session — never through the UI, which "proves
nothing" per the brief. MFA's equivalent test lives in
``keel.accounts.tests.test_mfa_flow`` (it needs ``allauth.mfa``
installed, which only happens under ``config.settings.test_mfa``).
"""

import pytest
from django.test import RequestFactory

from keel.accounts.models import User
from keel.billing.models import Plan, Price
from keel.core.exceptions import PermissionDeniedWithReason
from keel.core.impersonation import ImpersonationRestricted
from keel.organizations import services as org_services
from keel.organizations.models import Organization

pytestmark = pytest.mark.django_db


def _org() -> Organization:
    owner = User.objects.create_user(email="owner@example.com", password="s3cret-pass")
    return Organization.objects.create(name="Acme", slug="acme", created_by=owner)


def test_delete_organization_is_blocked_while_impersonating() -> None:
    org = _org()
    staff = User.objects.create_user(
        email="staff@example.com", password="s3cret-pass", is_staff=True
    )

    with pytest.raises(ImpersonationRestricted) as exc_info:
        org_services.delete_organization(organization=org, actor=org.created_by, impersonator=staff)

    assert exc_info.value.code == "impersonation_restricted"
    org.refresh_from_db()
    assert org.deleted_at is None


def test_delete_organization_succeeds_without_impersonation() -> None:
    org = _org()

    result = org_services.delete_organization(organization=org, actor=org.created_by)

    assert result.deleted_at is not None


def test_create_checkout_session_is_blocked_while_impersonating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from keel.billing import services as billing_services

    org = _org()
    staff = User.objects.create_user(
        email="staff2@example.com", password="s3cret-pass", is_staff=True
    )
    plan = Plan.objects.create(code="starter", name="Starter", stripe_product_id="prod_1")
    price = Price.objects.create(
        plan=plan,
        stripe_price_id="price_1",
        interval=Price.INTERVAL_MONTH,
        unit_amount=1900,
        currency="AUD",
    )

    def _fail_if_called(**kw: object) -> str:
        raise AssertionError("must not reach Stripe when impersonating")

    monkeypatch.setattr(
        "keel.billing.stripe_client.create_customer",
        _fail_if_called,
    )

    with pytest.raises(ImpersonationRestricted):
        billing_services.create_checkout_session(
            organization=org,
            actor=org.created_by,
            impersonator=staff,
            price=price,
            success_url="https://app.test/success",
            cancel_url="https://app.test/cancel",
        )


def test_create_portal_session_is_blocked_while_impersonating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from keel.billing import services as billing_services

    org = _org()
    org.stripe_customer_id = "cus_existing"
    org.save(update_fields=["stripe_customer_id"])
    staff = User.objects.create_user(
        email="staff3@example.com", password="s3cret-pass", is_staff=True
    )

    def _fail_if_called(**kw: object) -> str:
        raise AssertionError("must not reach Stripe when impersonating")

    monkeypatch.setattr("keel.billing.stripe_client.create_billing_portal_session", _fail_if_called)

    with pytest.raises(ImpersonationRestricted):
        billing_services.create_portal_session(
            organization=org,
            actor=org.created_by,
            impersonator=staff,
            return_url="https://app.test/billing",
        )


def test_password_change_is_blocked_while_impersonating() -> None:
    """``set_password`` (docs/plans/phase-8.md 8.3) is the one call point
    every allauth password flow — change, reset-confirm — goes through
    (``keel.notifications.adapter.KeelAccountAdapter``). ``self.request``
    on an allauth adapter comes from ``allauth.core.context.request`` —
    a contextvar allauth's own middleware populates on every real
    request — not from the constructor argument, so the test enters the
    same context manager that middleware uses."""
    from allauth.core.context import request_context

    from keel.core.impersonation import IMPERSONATOR_SESSION_KEY
    from keel.notifications.adapter import KeelAccountAdapter

    user = User.objects.create_user(email="target@example.com", password="s3cret-pass")
    staff = User.objects.create_user(
        email="staff4@example.com", password="s3cret-pass", is_staff=True
    )
    request = RequestFactory().post("/_allauth/browser/v1/account/password/change")
    _attach_session(request)
    request.session[IMPERSONATOR_SESSION_KEY] = staff.pk

    with request_context(request):
        adapter = KeelAccountAdapter()
        with pytest.raises(PermissionDeniedWithReason) as exc_info:
            adapter.set_password(user, "a-new-password-1")

    assert exc_info.value.code == "impersonation_restricted"
    user.refresh_from_db()
    assert not user.check_password("a-new-password-1")


def test_password_change_succeeds_without_impersonation() -> None:
    from allauth.core.context import request_context

    from keel.notifications.adapter import KeelAccountAdapter

    user = User.objects.create_user(email="target2@example.com", password="s3cret-pass")
    request = RequestFactory().post("/_allauth/browser/v1/account/password/change")
    _attach_session(request)

    with request_context(request):
        adapter = KeelAccountAdapter()
        adapter.set_password(user, "a-new-password-1")

    user.refresh_from_db()
    assert user.check_password("a-new-password-1")


def _attach_session(request: object) -> None:
    from django.contrib.sessions.backends.db import SessionStore

    request.session = SessionStore()  # type: ignore[attr-defined]
    request.session.create()  # type: ignore[attr-defined]
