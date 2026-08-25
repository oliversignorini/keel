"""Writes (PRD §4 "Data model"; docs/plans/phase-6.md 6.D). The
reference-slice's ``services.py`` — the shape ``/new-resource`` copies.

Same discipline as ``keel/organizations/services.py``: one
``transaction.atomic()`` per function, opened here and never in a view;
mutating functions are ``@audited`` or ``@not_audited(reason=...)``; a
quantity check (``check_limit``) happens before anything is written.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from keel.billing.entitlements import check_limit
from keel.core.audit import audited
from keel.organizations.models import Organization
from keel.widgets.models import Widget


def _notify_widget_created(widget_id: Any) -> None:
    """Seam for a downstream integration (search index, webhook, ...) —
    the same "documented no-op" pattern as
    ``organizations.services._sync_stripe_customer``. Nothing in this
    project actually needs one; this exists so ``/new-resource``'s copy
    has somewhere to put one."""


def _dispatch_widget_created(widget_id: Any) -> None:
    """Enqueues the Tier-1 notification task (``keel.widgets.tasks``) on
    commit — a lazy import because ``tasks.py`` imports this module at
    module level (PRD §4 invariant 5's "one-line delegation to services"
    means the task, not this service, owns the enqueue direction)."""
    from keel.widgets.tasks import notify_widget_created_task

    notify_widget_created_task.enqueue(str(widget_id))


@audited("widget.created")
def create_widget(
    *, organization: Organization, name: str, description: str, status: str, created_by: Any
) -> Widget:
    check_limit(organization, "widgets")
    with transaction.atomic():
        widget = Widget.objects.create(
            organization=organization,
            name=name,
            description=description,
            status=status,
            created_by=created_by,
        )
        transaction.on_commit(lambda: _dispatch_widget_created(widget.id))
    return widget


@audited("widget.updated")
def update_widget(*, widget: Widget, actor: Any, impersonator: Any = None, **fields: Any) -> Widget:
    with transaction.atomic():
        for field, value in fields.items():
            setattr(widget, field, value)
        widget.save(update_fields=list(fields))
    return widget


@audited("widget.deleted")
def delete_widget(*, widget: Widget, actor: Any, impersonator: Any = None) -> None:
    with transaction.atomic():
        widget.delete()
