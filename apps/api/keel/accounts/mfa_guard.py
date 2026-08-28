"""Blocks MFA management during an impersonated session (PRD §6 "cannot
... manage MFA").

``allauth.mfa`` is installed only when ``KEEL_MFA_ENABLED`` is set
(``config/settings/base.py``), so this module is imported and wired from
``AccountsConfig.ready()`` behind the same flag — it imports
``allauth.mfa.models.Authenticator``, which doesn't exist otherwise.

Every add, replace, or removal of an authenticator — TOTP activation,
recovery-code regeneration, a WebAuthn key — is a write to this one
model, regardless of which allauth view or headless endpoint it came
from. Hooking ``pre_save``/``pre_delete`` here, instead of chasing each
allauth view/adapter method individually, covers all of them by
construction and is exactly as directly testable at the model layer as
calling a service: ``Authenticator.objects.create(...)`` with the
impersonation contextvar set is the unit test, no HTTP required.
"""

from typing import Any

from django.db.models.signals import pre_delete, pre_save

from keel.core.impersonation import forbid_when_impersonating, get_current_impersonator_id


def connect() -> None:
    """Called once from ``AccountsConfig.ready()``, behind
    ``KEEL_MFA_ENABLED`` — see this module's docstring."""
    from allauth.mfa.models import Authenticator

    pre_save.connect(
        _forbid_authenticator_write, sender=Authenticator, dispatch_uid="mfa_guard_save"
    )
    pre_delete.connect(
        _forbid_authenticator_write, sender=Authenticator, dispatch_uid="mfa_guard_delete"
    )


def _forbid_authenticator_write(sender: Any, instance: Any, **kwargs: Any) -> None:
    forbid_when_impersonating(get_current_impersonator_id(), "manage MFA")
