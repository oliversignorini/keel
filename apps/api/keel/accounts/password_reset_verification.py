"""Wires ``keel.accounts.services.verify_email_after_password_reset`` onto
allauth's ``password_reset`` signal — see that function's docstring for
why. Connected unconditionally from ``AccountsConfig.ready()`` (unlike
``mfa_guard``, this doesn't depend on an optional app being installed).
"""

from typing import Any

from allauth.account.signals import password_reset

from keel.accounts.services import verify_email_after_password_reset


def connect() -> None:
    """Called once from ``AccountsConfig.ready()``."""
    password_reset.connect(
        _on_password_reset, dispatch_uid="accounts_verify_email_on_password_reset"
    )


def _on_password_reset(sender: Any, request: Any, user: Any, **kwargs: Any) -> None:
    verify_email_after_password_reset(user=user, actor=user)
