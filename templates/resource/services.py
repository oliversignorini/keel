"""Writes (PRD §4 "Data model"; CLAUDE.md invariants 3 and 7).

The discipline this file exists to hold: one ``transaction.atomic()`` per
function, opened here and never in a view; every mutating function is
``@audited`` or ``@not_audited(reason=...)``; a quantity check
(``check_limit``) happens before anything is written; anything external
(Stripe, a webhook, a search index) goes through
``transaction.on_commit()`` rather than running inside the open
transaction.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from keel.__app__.models import __Resource__
from keel.billing.entitlements import check_limit
from keel.core.audit import audited
from keel.organizations.models import Organization


def _notify___resource___created(__resource___id: Any) -> None:
    """Seam for a downstream integration (search index, webhook, ...) —
    the same "documented no-op" pattern as
    ``organizations.services._sync_stripe_customer``. Fill it in or delete
    it; leaving it empty is a deliberate third option."""


def _dispatch___resource___created(__resource___id: Any) -> None:
    """Enqueues the Tier-1 notification task (``keel.__app__.tasks``) on
    commit — a lazy import because ``tasks.py`` imports this module at
    module level (CLAUDE.md invariant 5's "one-line delegation to
    services" means the task, not this service, owns the enqueue
    direction)."""
    from keel.__app__.tasks import notify___resource___created_task

    notify___resource___created_task.enqueue(str(__resource___id))


@audited("__resource__.created")
def create___resource__(
    *,
    organization: Organization,
    # keel:insert create_params
    created_by: Any,
) -> __Resource__:
    check_limit(organization, "__app__")
    with transaction.atomic():
        __resource__ = __Resource__.objects.create(
            organization=organization,
            # keel:insert create_kwargs
            created_by=created_by,
        )
        transaction.on_commit(lambda: _dispatch___resource___created(__resource__.id))
    return __resource__


@audited("__resource__.updated")
def update___resource__(
    *, __resource__: __Resource__, actor: Any, impersonator: Any = None, **fields: Any
) -> __Resource__:
    with transaction.atomic():
        for field, value in fields.items():
            setattr(__resource__, field, value)
        __resource__.save(update_fields=list(fields))
    return __resource__


@audited("__resource__.deleted")
def delete___resource__(
    *, __resource__: __Resource__, actor: Any, impersonator: Any = None
) -> None:
    with transaction.atomic():
        __resource__.delete()
