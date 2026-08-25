"""Test settings with TOTP MFA switched on (PRD §8 Phase 2 A.4: "TOTP
enrolment and challenge work when the flag is enabled, and the endpoints
are absent when it is not").

``allauth.mfa`` is only added to INSTALLED_APPS when KEEL_MFA_ENABLED is
true at settings-load time (config/settings/base.py) — Django's app
registry is fixed once ``django.setup()`` runs, so this can't be toggled
mid-suite with ``override_settings``. The default test suite (config.
settings.test) runs with the flag off and asserts the endpoints are
absent; keel/accounts/tests/test_mfa_flow.py's tests are collected only
when running under *this* settings module (see that file's skip guard),
exercised via:

    uv run pytest keel/accounts/tests/test_mfa_flow.py --ds=config.settings.test_mfa
"""

from .test import *  # noqa: F403

KEEL_MFA_ENABLED = True
INSTALLED_APPS = [*INSTALLED_APPS, "allauth.mfa"]  # noqa: F405
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
