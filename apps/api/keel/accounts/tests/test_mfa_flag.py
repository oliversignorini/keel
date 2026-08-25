"""Runs under the default test settings (KEEL_MFA_ENABLED=false). The
"flag on" half of this acceptance criterion lives in test_mfa_flow.py,
which only collects under config.settings.test_mfa — see that file."""

import pytest
from django.conf import settings
from django.test import Client


def test_mfa_is_off_by_default_in_test_settings() -> None:
    assert settings.KEEL_MFA_ENABLED is False
    assert "allauth.mfa" not in settings.INSTALLED_APPS


@pytest.mark.django_db
def test_totp_endpoints_are_absent_when_the_flag_is_off() -> None:
    client = Client()

    response = client.get("/_allauth/browser/v1/account/authenticators/totp")

    assert response.status_code == 404


@pytest.mark.django_db
def test_config_endpoint_has_no_mfa_key_when_the_flag_is_off() -> None:
    client = Client()

    response = client.get("/_allauth/browser/v1/config")

    assert "mfa" not in response.json()["data"]
