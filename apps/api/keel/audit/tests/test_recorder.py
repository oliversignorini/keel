"""The real ``AuditLog`` writer, wired at app-ready time (PRD v1.2 §8
Phase 8; docs/plans/phase-8.md 8.1's acceptance criterion: "An audited
service writes exactly one audit row per call, on commit, carrying actor
and impersonator")."""

import pytest
from django.db import transaction

from keel.accounts.models import User
from keel.audit.models import AuditLog
from keel.organizations import services
from keel.organizations.models import Organization

pytestmark = pytest.mark.django_db(transaction=True)


def _org() -> Organization:
    owner = User.objects.create_user(email="owner@example.com", password="s3cret-pass")
    return Organization.objects.create(name="Acme", slug="acme", created_by=owner)


def test_audited_service_writes_exactly_one_row_on_commit_with_actor(
    django_capture_on_commit_callbacks,
) -> None:
    org = _org()
    actor = User.objects.create_user(email="actor@example.com", password="s3cret-pass")

    with django_capture_on_commit_callbacks(execute=True):
        services.update_organization(organization=org, actor=actor, name="Acme Renamed")

    rows = AuditLog.objects.filter(action="organization.updated")
    assert rows.count() == 1
    row = rows.get()
    assert row.actor_id == actor.pk
    assert row.impersonator_id is None
    assert row.organization_id == org.pk


def test_audit_row_rolls_back_with_the_effect_it_records() -> None:
    """ddia#17: the audit write is inline, inside the same transaction as
    the effect it describes — not a dual write via ``on_commit()``. If
    the surrounding transaction rolls back, the audit row must roll back
    with it; there is no window where the effect is durable and the
    audit row is silently lost, or vice versa."""
    org = _org()
    actor = User.objects.create_user(email="actor2@example.com", password="s3cret-pass")

    class _Boom(Exception):
        pass

    with pytest.raises(_Boom), transaction.atomic():
        services.update_organization(organization=org, actor=actor, name="Not Committed")
        raise _Boom()

    assert not AuditLog.objects.filter(action="organization.updated").exists()
    org.refresh_from_db()
    assert org.name != "Not Committed"


def test_audited_service_records_the_impersonator(django_capture_on_commit_callbacks) -> None:
    """Proves the recorder's impersonator handling (docs/plans/phase-8.md
    8.1) against a service the PRD §6 restrictions don't cover — widget
    CRUD isn't one of the four restricted actions, so an impersonated
    session performing it is exactly the case PRD §6 says must still be
    recorded ("every subsequent AuditLog row carries impersonator")."""
    from keel.widgets import services as widget_services
    from keel.widgets.models import Widget

    org = _org()
    actor = User.objects.create_user(email="actor3@example.com", password="s3cret-pass")
    staff = User.objects.create_user(
        email="staff@example.com", password="s3cret-pass", is_staff=True
    )
    widget = Widget.objects.create(
        organization=org, name="Old name", description="", status="active", created_by=actor
    )

    with django_capture_on_commit_callbacks(execute=True):
        widget_services.update_widget(
            widget=widget, actor=actor, impersonator=staff, name="New name"
        )

    row = AuditLog.objects.get(action="widget.updated", target_id=str(widget.pk))
    assert row.actor_id == actor.pk
    assert row.impersonator_id == staff.pk
