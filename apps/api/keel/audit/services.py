"""Audit log retention (PRD §5 "Scheduled jobs"), weekly — plus the two
impersonation records, which have no other service to live in.

Every write to ``AuditLog`` goes through ``keel.core.audit``'s recorder
seam (``@audited`` → ``keel.audit.recorder``); a view or an admin action
calling ``AuditLog.objects.create()`` itself bypasses that seam, so the
one place the row's shape is decided stops being the one place it is
decided."""

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from keel.audit.models import AuditLog
from keel.core.audit import audited, not_audited


@not_audited(
    reason="Scheduled system job (PRD §5), not a user action — no actor to record. "
    "Also avoids the absurdity of an AuditLog-purging function writing to the "
    "table it is purging."
)
def purge_old_audit_logs() -> int:
    """Deletes ``AuditLog`` rows older than
    ``settings.AUDIT_LOG_RETENTION_DAYS``. Idempotent by construction:
    the cutoff only ever matches rows not yet deleted, so a second run
    in the same window deletes zero."""
    cutoff = timezone.now() - timedelta(days=settings.AUDIT_LOG_RETENTION_DAYS)
    deleted, _ = AuditLog.objects.filter(created_at__lt=cutoff).delete()
    return deleted


@audited("impersonation.start")
def record_impersonation_start(*, actor: Any, impersonator: Any, target: Any) -> Any:
    """Records that ``impersonator`` began impersonating ``actor`` (PRD §6).

    The effect itself — logging the browser session in as the target —
    needs the ``request`` object, which a service never takes (invariant
    3), so it stays in ``keel.core.impersonation.start_impersonation``
    and this service records it. The row is written by ``@audited`` alone:
    the recorder seam, not an inline ``AuditLog.objects.create()`` in the
    admin action."""
    return target


@audited("impersonation.end")
def record_impersonation_end(*, actor: Any, impersonator: Any, target: Any) -> Any:
    """The other half of ``record_impersonation_start`` — same division
    of labour: ``keel.core.impersonation.end_impersonation`` unwinds the
    session, this records it."""
    return target
