"""TOTP enrolment and challenge, run only with the flag on (PRD §8 Phase 2
A.4). ``allauth.mfa`` is only in INSTALLED_APPS when KEEL_MFA_ENABLED was
true at settings-load time (see config/settings/test_mfa.py's docstring),
so this whole module is skipped under the default test settings rather
than collected-and-failing.

    uv run pytest keel/accounts/tests/test_mfa_flow.py --ds=config.settings.test_mfa
"""

import base64
import hashlib
import hmac
import re
import struct
import time
from urllib.parse import unquote

import pytest
from django.conf import settings
from django.core import mail
from django.test import Client

pytestmark = [
    pytest.mark.skipif(
        not settings.KEEL_MFA_ENABLED,
        reason="MFA is off — run with DJANGO_SETTINGS_MODULE=config.settings.test_mfa",
    ),
    pytest.mark.django_db(transaction=True),
]


def _totp_code(secret: str, digits: int = 6, period: int = 30) -> str:
    """RFC 6238, matching allauth.mfa.totp.internal.auth.hotp_value."""
    counter = int(time.time()) // period
    counter_bytes = struct.pack(">Q", counter)
    key = base64.b32decode(secret.encode("ascii"), casefold=True)
    digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = bytearray(digest[offset : offset + 4])
    truncated[0] &= 0x7F
    value = struct.unpack(">I", truncated)[0] % (10**digits)
    return f"{value:0{digits}}"


def _signup_verify_login(client: Client, email: str, password: str) -> None:
    client.post(
        "/_allauth/browser/v1/auth/signup",
        {"email": email, "password": password},
        content_type="application/json",
    )
    match = re.search(r"verify-email/(\S+)", str(mail.outbox[-1].body))
    assert match, "no verify-email link found in email body"
    key = unquote(match.group(1))
    client.post(
        "/_allauth/browser/v1/auth/email/verify", {"key": key}, content_type="application/json"
    )
    response = client.post(
        "/_allauth/browser/v1/auth/login",
        {"email": email, "password": password},
        content_type="application/json",
    )
    assert response.status_code == 200, response.json()


def test_totp_enrolment() -> None:
    client = Client()
    _signup_verify_login(client, "ada@example.com", "s3cret-pass-1")

    secret_response = client.get("/_allauth/browser/v1/account/authenticators/totp")
    assert secret_response.status_code == 404, secret_response.json()  # not yet enrolled
    secret = secret_response.json()["meta"]["secret"]

    activate_response = client.post(
        "/_allauth/browser/v1/account/authenticators/totp",
        {"code": _totp_code(secret)},
        content_type="application/json",
    )

    assert activate_response.status_code == 200, activate_response.json()
    assert activate_response.json()["data"]["type"] == "totp"


def test_totp_challenge_on_next_login() -> None:
    client = Client()
    _signup_verify_login(client, "ada@example.com", "s3cret-pass-1")
    secret = client.get("/_allauth/browser/v1/account/authenticators/totp").json()["meta"]["secret"]
    client.post(
        "/_allauth/browser/v1/account/authenticators/totp",
        {"code": _totp_code(secret)},
        content_type="application/json",
    )
    client.delete("/_allauth/browser/v1/auth/session")

    login_response = client.post(
        "/_allauth/browser/v1/auth/login",
        {"email": "ada@example.com", "password": "s3cret-pass-1"},
        content_type="application/json",
    )

    assert login_response.status_code == 401, login_response.json()
    flows = login_response.json()["data"]["flows"]
    pending = next(f for f in flows if f["id"] == "mfa_authenticate")
    assert pending["is_pending"] is True

    challenge_response = client.post(
        "/_allauth/browser/v1/auth/2fa/authenticate",
        {"code": _totp_code(secret)},
        content_type="application/json",
    )

    assert challenge_response.status_code == 200, challenge_response.json()
    assert challenge_response.json()["meta"]["is_authenticated"] is True


# --- Impersonation restriction (PRD §6; docs/plans/phase-8.md 8.3) -----


def test_authenticator_writes_are_blocked_while_impersonating() -> None:
    """Direct, model-layer proof (the "call the service directly with an
    impersonated session" test docs/plans/phase-8.md 8.3 asks for) —
    every add/replace/remove of an ``Authenticator`` goes through
    ``Authenticator.save()``/``.delete()``, which ``keel.accounts.mfa_guard``
    hooks unconditionally. No HTTP request needed to prove the block; the
    HTTP-level version follows below."""
    from allauth.mfa.models import Authenticator

    from keel.accounts.models import User
    from keel.core.exceptions import PermissionDeniedWithReason
    from keel.core.impersonation import _current_impersonator_id

    user = User.objects.create_user(email="dana@example.com", password="s3cret-pass-1")
    token = _current_impersonator_id.set("staff-marker")
    try:
        with pytest.raises(PermissionDeniedWithReason):
            Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={})
    finally:
        _current_impersonator_id.reset(token)
    assert not Authenticator.objects.filter(user=user).exists()


def test_totp_enrolment_is_blocked_over_http_while_impersonating() -> None:
    """The HTTP-level companion: a session flagged as impersonating (the
    same session key ``keel.core.impersonation.start_impersonation``
    writes) cannot complete TOTP activation through the real headless
    endpoint. ``raise_request_exception=False`` because the guard's
    exception is deliberately not one allauth's own view code catches —
    the point is that the write never lands, not that this endpoint
    renders it as a pretty 403."""
    client = Client(raise_request_exception=False)
    _signup_verify_login(client, "grace@example.com", "s3cret-pass-1")
    secret = client.get("/_allauth/browser/v1/account/authenticators/totp").json()["meta"]["secret"]
    session = client.session
    session["impersonator_id"] = "staff-marker"
    session.save()

    activate_response = client.post(
        "/_allauth/browser/v1/account/authenticators/totp",
        {"code": _totp_code(secret)},
        content_type="application/json",
    )

    assert activate_response.status_code >= 400
