"""The six scheduled jobs (PRD §5 "Scheduled jobs"; docs/plans/phase-5.md
5.4). Each job is run twice and asserted to reach identical final state —
same shape as Phase 4's webhook replay tests."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core import mail
from django.utils import timezone

from keel.audit.models import AuditLog
from keel.billing.models import Plan, Price, Subscription
from keel.billing.tests.factories import make_organization
from keel.jobs import tasks
from keel.organizations.models import Invitation, Role

pytestmark = pytest.mark.django_db


def _make_role(organization) -> Role:
    return Role.objects.create(organization=organization, name="Member", permissions=[])


def _make_plan_and_price() -> Price:
    plan = Plan.objects.create(code="pro", name="Pro")
    return Price.objects.create(
        plan=plan, stripe_price_id="price_1", interval=Price.INTERVAL_MONTH, unit_amount=1000
    )


def _make_subscription(organization, *, status: str = "active", trial_end=None) -> Subscription:
    price = _make_plan_and_price()
    return Subscription.objects.create(
        organization=organization,
        stripe_subscription_id=f"sub_{organization.pk}",
        plan=price.plan,
        price=price,
        status=status,
        trial_end=trial_end,
    )


class TestSyncStripePlansTask:
    def test_idempotent_when_run_twice(self) -> None:
        products = [
            {
                "id": "prod_1",
                "name": "Pro",
                "metadata": {"code": "pro"},
                "prices": [
                    {
                        "id": "price_1",
                        "unit_amount": 1000,
                        "currency": "usd",
                        "recurring": {"interval": "month"},
                    }
                ],
            }
        ]
        with patch("keel.billing.stripe_client.fetch_products_and_prices", return_value=products):
            tasks.sync_stripe_plans_task()
            first_state = list(Plan.objects.values("code", "name", "is_active"))

            tasks.sync_stripe_plans_task()
            second_state = list(Plan.objects.values("code", "name", "is_active"))

        assert first_state == second_state == [{"code": "pro", "name": "Pro", "is_active": True}]


class TestExpireInvitationsTask:
    def test_idempotent_when_run_twice(self) -> None:
        organization = make_organization()
        role = _make_role(organization)
        invitation = Invitation.objects.create(
            organization=organization,
            email="invitee@example.com",
            role=role,
            token="tok",
            invited_by=organization.created_by,
            expires_at=timezone.now() - timedelta(days=1),
        )

        tasks.expire_invitations_task()
        invitation.refresh_from_db()
        first_revoked_at = invitation.revoked_at
        assert first_revoked_at is not None

        tasks.expire_invitations_task()
        invitation.refresh_from_db()

        assert invitation.revoked_at == first_revoked_at


class TestSendTrialEndingNoticesTask:
    def test_idempotent_when_run_twice(self) -> None:
        organization = make_organization()
        _make_subscription(organization, trial_end=timezone.now() + timedelta(days=1))

        tasks.send_trial_ending_notices_task()
        assert len(mail.outbox) == 1

        tasks.send_trial_ending_notices_task()
        assert len(mail.outbox) == 1  # no second send

        assert AuditLog.objects.filter(action="trial_ending_notice_sent").count() == 1


class TestCheckDunningTask:
    def test_idempotent_when_run_twice(self) -> None:
        organization = make_organization()
        _make_subscription(organization, status="past_due")

        tasks.check_dunning_task()
        assert len(mail.outbox) == 1

        tasks.check_dunning_task()
        assert len(mail.outbox) == 1

        assert AuditLog.objects.filter(action="dunning_notice_sent").count() == 1


class TestPurgeOldAuditLogsTask:
    def test_idempotent_when_run_twice(self, settings) -> None:
        settings.AUDIT_LOG_RETENTION_DAYS = 30
        old_log = AuditLog.objects.create(action="old.action")
        AuditLog.objects.filter(pk=old_log.pk).update(
            created_at=timezone.now() - timedelta(days=60)
        )
        recent_log = AuditLog.objects.create(action="recent.action")

        tasks.purge_old_audit_logs_task()
        first_ids = set(AuditLog.objects.values_list("pk", flat=True))
        assert first_ids == {recent_log.pk}

        tasks.purge_old_audit_logs_task()
        second_ids = set(AuditLog.objects.values_list("pk", flat=True))
        assert second_ids == first_ids


class TestCleanupExpiredSessionsTask:
    def test_idempotent_when_run_twice(self) -> None:
        from django.contrib.sessions.models import Session

        Session.objects.create(
            session_key="expired",
            session_data="",
            expire_date=timezone.now() - timedelta(days=1),
        )
        Session.objects.create(
            session_key="alive",
            session_data="",
            expire_date=timezone.now() + timedelta(days=1),
        )

        tasks.cleanup_expired_sessions_task()
        first_keys = set(Session.objects.values_list("session_key", flat=True))
        assert first_keys == {"alive"}

        tasks.cleanup_expired_sessions_task()
        second_keys = set(Session.objects.values_list("session_key", flat=True))
        assert second_keys == first_keys
