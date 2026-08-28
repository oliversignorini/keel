"""Expired session cleanup (PRD §5 "Scheduled jobs"; docs/plans/phase-5.md
5.4), daily. A system action — no actor to record."""

from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.core.management import call_command
from django.db import transaction

from keel.core.audit import audited, not_audited


@not_audited(reason="Scheduled system job (PRD §5), not a user action — no actor to record.")
def cleanup_expired_sessions() -> None:
    """Delegates to Django's own ``clearsessions`` management command
    rather than reimplementing its query — that command already deletes
    every ``django.contrib.sessions.models.Session`` row past its
    ``expire_date``, which is exactly this job's brief. Idempotent by
    construction: a second run finds nothing left to delete."""
    call_command("clearsessions")


@audited("account.email_verified_via_password_reset")
def verify_email_after_password_reset(*, user: AbstractBaseUser, actor: Any = None) -> Any:
    """Wired to allauth's ``password_reset`` signal (see
    ``keel.accounts.password_reset_verification``). Successfully setting
    a new password from the emailed reset key is itself proof of inbox
    access — the same proof ``ACCOUNT_EMAIL_VERIFICATION = "mandatory"``
    otherwise demands via the separate confirmation email — so this marks
    the account's primary address verified in the same request, before
    ``ACCOUNT_LOGIN_ON_PASSWORD_RESET`` tries to log the user in. Without
    it, mandatory verification would still route a reset for a
    never-verified address into a fresh "verify your email" gate instead
    of finishing the login."""
    from allauth.account.models import EmailAddress

    with transaction.atomic():
        address = EmailAddress.objects.filter(user=user, primary=True).first()
        if address and not address.verified:
            address.verified = True
            address.save(update_fields=["verified"])
        return address
