"""The real ``AuditLog`` writer (PRD v1.2 §8 Phase 8; docs/plans/phase-8.md
8.1). Installed against ``keel.core.audit.set_recorder`` at app-ready
time — see ``AuditConfig.ready``. Until this module is imported, every
``@audited`` call is a no-op (the seam Phase 1 documented, "nothing
writes to it until Phase 8 wires ``set_recorder`` to a real writer").

``AuditRecord`` carries no ``organization``, ``ip`` or ``user_agent`` —
those fields live on request context that the decorator, deliberately, is
never given (PRD §4 invariant 3: services take model instances and
plain values, never the request). This recorder resolves an organisation
from whatever ``target`` the service passed — a row with an
``organization_id``, or an ``Organization`` itself — and leaves the row's
``ip``/``user_agent`` blank rather than guess. Django admin's
"Impersonate" action (``keel.audit.impersonation``) is the one call site
that has a real request and passes ``ip``/``user_agent`` in ``metadata``
instead, since ``AuditRecord`` has nowhere else to put them.
"""

from typing import Any

from keel.accounts.models import User
from keel.audit.models import AuditLog
from keel.core.audit import AuditRecord
from keel.organizations.models import Organization


def _resolve_actor(value: Any) -> User | None:
    return value if isinstance(value, User) else None


def _resolve_organization(target: Any) -> Organization | None:
    if isinstance(target, Organization):
        return target
    organization = getattr(target, "organization", None)
    return organization if isinstance(organization, Organization) else None


def _target_type_and_id(target: Any) -> tuple[str, str]:
    if target is None:
        return "", ""
    pk = getattr(target, "pk", None)
    if pk is not None:
        return type(target).__name__, str(pk)
    return type(target).__name__, str(target)


def record_audit_event(record: AuditRecord) -> None:
    """The function installed as ``keel.core.audit``'s recorder. One
    ``AuditLog`` row per call — this function is only ever reached from
    inside ``@audited``'s ``transaction.on_commit()`` callback, so a
    single service call that commits produces exactly one row here."""
    target_type, target_id = _target_type_and_id(record.target)
    metadata = dict(record.metadata or {})
    ip = metadata.pop("ip", None)
    user_agent = metadata.pop("user_agent", "")
    AuditLog.objects.create(
        organization=_resolve_organization(record.target),
        actor=_resolve_actor(record.actor),
        impersonator=_resolve_actor(record.impersonator),
        action=record.action,
        target_type=target_type,
        target_id=target_id,
        metadata=metadata,
        ip=ip,
        user_agent=user_agent,
    )
