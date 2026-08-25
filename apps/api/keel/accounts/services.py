"""Expired session cleanup (PRD §5 "Scheduled jobs"; docs/plans/phase-5.md
5.4), daily. A system action — no actor to record."""

from django.core.management import call_command

from keel.core.audit import not_audited


@not_audited(reason="Scheduled system job (PRD §5), not a user action — no actor to record.")
def cleanup_expired_sessions() -> None:
    """Delegates to Django's own ``clearsessions`` management command
    rather than reimplementing its query — that command already deletes
    every ``django.contrib.sessions.models.Session`` row past its
    ``expire_date``, which is exactly this job's brief. Idempotent by
    construction: a second run finds nothing left to delete."""
    call_command("clearsessions")
