"""The six scheduled jobs (PRD §5 "Scheduled jobs"; docs/plans/phase-5.md
5.4), wired into ``CELERY_BEAT_SCHEDULE`` (config/settings/base.py).

Each is a Tier-1 ``@task`` whose body is a single call into the service
that actually does the work — the services themselves (in
``keel.billing``, ``keel.organizations``, ``keel.audit``,
``keel.accounts``) are what's idempotent-when-run-twice; these wrappers
just give each one a Celery task name and the shim's retry/dead-letter
policy. None of the six take any argument — they operate over every
matching row, not one row at an id — so the "tasks take ids, never
model instances" rule is trivially satisfied here.
"""

from keel.core.tasks import task


@task
def sync_stripe_plans_task() -> None:
    from keel.billing.services import sync_stripe_plans

    sync_stripe_plans()


@task
def expire_invitations_task() -> None:
    from keel.organizations.services import expire_invitations

    expire_invitations()


@task
def send_trial_ending_notices_task() -> None:
    from keel.billing.services import send_trial_ending_notices

    send_trial_ending_notices()


@task
def check_dunning_task() -> None:
    from keel.billing.services import check_dunning

    check_dunning()


@task
def purge_old_audit_logs_task() -> None:
    from keel.audit.services import purge_old_audit_logs

    purge_old_audit_logs()


@task
def cleanup_expired_sessions_task() -> None:
    from keel.accounts.services import cleanup_expired_sessions

    cleanup_expired_sessions()
