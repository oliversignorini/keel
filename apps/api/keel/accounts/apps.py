from django.apps import AppConfig
from django.conf import settings


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "keel.accounts"

    def ready(self) -> None:
        # Wires the impersonation restriction onto MFA management (PRD
        # §6; docs/plans/phase-8.md 8.3) — only meaningful, and only
        # importable, once allauth.mfa itself is installed.
        if getattr(settings, "KEEL_MFA_ENABLED", False):
            from keel.accounts import mfa_guard

            mfa_guard.connect()
