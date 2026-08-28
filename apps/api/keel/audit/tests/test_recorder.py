"""The real ``AuditLog`` writer, wired at app-ready time (PRD v1.2 §8's
acceptance criterion: "An audited service writes exactly one audit row
per call, on commit, carrying actor and impersonator")."""

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
    """Proves the recorder's impersonator handling against a service the
    PRD §6 restrictions don't cover — widget
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


def test_created_rows_carry_the_actor(django_capture_on_commit_callbacks) -> None:
    """The creating services name their actor ``actor``, not after the
    ``created_by``/``invited_by`` model field it lands in — ``@audited``
    reads ``kwargs["actor"]``, so a mismatched parameter name writes the
    row with ``actor=NULL`` and the audit trail can't say who did it."""
    from keel.widgets import services as widget_services

    owner = User.objects.create_user(email="creator@example.com", password="s3cret-pass")

    with django_capture_on_commit_callbacks(execute=True):
        org = services.create_organization(name="Created Co", slug="created-co", actor=owner)
        widget = widget_services.create_widget(
            organization=org, name="A widget", description="", status="active", actor=owner
        )

    org_row = AuditLog.objects.get(action="organization.created", target_id=str(org.pk))
    assert org_row.actor_id == owner.pk
    assert org_row.organization_id == org.pk

    widget_row = AuditLog.objects.get(action="widget.created", target_id=str(widget.pk))
    assert widget_row.actor_id == owner.pk
    assert widget_row.organization_id == org.pk


def test_deleted_rows_name_the_target_and_its_organization(
    django_capture_on_commit_callbacks,
) -> None:
    """A delete service returning ``None`` leaves ``@audited`` with no
    target: ``target_type``/``target_id`` blank and ``organization``
    null, so the row says nothing about *what* was deleted. The deleted
    row is returned instead, pk intact."""
    from keel.widgets import services as widget_services
    from keel.widgets.models import Widget

    org = _org()
    actor = User.objects.create_user(email="deleter@example.com", password="s3cret-pass")
    widget = Widget.objects.create(
        organization=org, name="Doomed", description="", status="active", created_by=actor
    )
    widget_pk = widget.pk

    with django_capture_on_commit_callbacks(execute=True):
        widget_services.delete_widget(widget=widget, actor=actor)

    assert not Widget.objects.filter(pk=widget_pk).exists()
    row = AuditLog.objects.get(action="widget.deleted")
    assert row.target_type == "Widget"
    assert row.target_id == str(widget_pk)
    assert row.organization_id == org.pk
    assert row.actor_id == actor.pk


def test_removed_membership_rows_name_the_membership_and_its_organization(
    django_capture_on_commit_callbacks,
) -> None:
    """The same gap as ``delete_widget``'s, for the other delete service
    in the codebase that used to return ``None``."""
    from keel.organizations.models import Membership

    owner = User.objects.create_user(email="owner-rm@example.com", password="s3cret-pass")
    second = User.objects.create_user(email="second-rm@example.com", password="s3cret-pass")
    with django_capture_on_commit_callbacks(execute=True):
        org = services.create_organization(name="Removals", slug="removals", actor=owner)
    owner_membership = Membership.objects.get(organization=org, user=owner)
    second_membership = Membership.objects.create(
        organization=org,
        user=second,
        role=owner_membership.role,
        status=Membership.STATUS_ACTIVE,
    )
    membership_pk = second_membership.pk

    with django_capture_on_commit_callbacks(execute=True):
        services.remove_member(membership=second_membership, actor=owner)

    assert not Membership.objects.filter(pk=membership_pk).exists()
    row = AuditLog.objects.get(action="membership.removed")
    assert row.target_type == "Membership"
    assert row.target_id == str(membership_pk)
    assert row.organization_id == org.pk
    assert row.actor_id == owner.pk
