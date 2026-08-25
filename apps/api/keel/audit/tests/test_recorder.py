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


def test_row_is_not_written_before_commit() -> None:
    """``update_organization`` opens and closes its own ``atomic()``
    block before returning (PRD §4 invariant 3), so proving "not before
    commit" needs an *outer* atomic block wrapping the whole call — same
    shape as ``keel.core.tests.test_audit``'s
    ``test_audited_does_not_record_before_commit`` — rather than
    ``django_capture_on_commit_callbacks``: with no surrounding atomic,
    ``transaction.on_commit()`` runs its callback immediately once the
    service's own block closes, which the capture fixture never sees."""
    org = _org()
    actor = User.objects.create_user(email="actor2@example.com", password="s3cret-pass")

    with transaction.atomic():
        services.update_organization(organization=org, actor=actor, name="Not Yet")
        assert not AuditLog.objects.filter(action="organization.updated").exists()

    assert AuditLog.objects.filter(action="organization.updated").exists()


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
