"""Audit log retention (PRD §5 "Scheduled jobs"), weekly. A system
action — no actor to record."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from keel.audit.models import AuditLog
from keel.core.audit import not_audited


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
