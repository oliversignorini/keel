"""End-to-end auth flows through the real HTTP stack (PRD §8).

Every test goes through django.test.Client against the actual URLconf —
no mocking of allauth's own views — because the thing worth verifying is
the wiring (settings, middleware, URLs) as much as allauth's behavior
itself.
"""

import re
from urllib.parse import unquote

import pytest
from django.core import mail
from django.test import Client

pytestmark = pytest.mark.django_db(transaction=True)
# transaction=True: allauth sends confirmation/reset emails from
# transaction.on_commit(), which a non-transactional test's rolled-back
# outer transaction never fires — these tests need the email to actually
# land in mail.outbox to extract the key from it.


def _extract_key(email_body: object, path: str) -> str:
    match = re.search(rf"{re.escape(path)}/(\S+)", str(email_body))
    assert match, f"no {path} link found in email body:\n{email_body}"
    return unquote(match.group(1))


def _signup_and_verify(client, email: str, password: str) -> None:
    response = client.post(
        "/_allauth/browser/v1/auth/signup",
        {"email": email, "password": password},
        content_type="application/json",
    )
    assert response.status_code == 401, response.json()
    key = _extract_key(mail.outbox[-1].body, "verify-email")
    response = client.post(
        "/_allauth/browser/v1/auth/email/verify",
        {"key": key},
        content_type="application/json",
    )
    # Deterministic 200, not the old (200, 401) tolerance: ACCOUNT_LOGIN_
    # ON_EMAIL_CONFIRMATION (config/settings/base.py) means clicking the
    # link authenticates the session as part of the same call — the
    # client is logged in by the time this returns, which every caller
    # below that wants a *fresh* explicit login now has to `client.logout()`
    # first, or it gets a 409 (already authenticated) instead of 200.
    assert response.status_code == 200, response.json()


def test_signup_leaves_the_address_unverified_until_the_link_is_clicked() -> None:
    """Regression test: a fresh signup's ``EmailAddress`` must come back
    ``verified=False`` — the actual finding behind an earlier report's
    "verified=True immediately" claim turned out to be a misdiagnosis
    (see docs/review-2026-08.md's e2e/auth-flows.spec.ts entry and this
    fix's commit): the address genuinely starts unverified, and the
    thing that was really broken was the frontend not decoding the
    emailed key before sending it back (apps/web/app/(auth)/verify-email/
    [key]/page.tsx), plus two missing ACCOUNT_LOGIN_ON_* settings. This
    pins the one fact the original report got right so a real regression
    here — some future signal or adapter override marking the address
    verified up front — still fails loudly."""
    from allauth.account.models import EmailAddress
    from django.test import Client

    client = Client()
    response = client.post(
        "/_allauth/browser/v1/auth/signup",
        {"email": "ada@example.com", "password": "s3cret-pass-1"},
        content_type="application/json",
    )
    assert response.status_code == 401, response.json()

    address = EmailAddress.objects.get(email="ada@example.com")
    assert address.verified is False

    key = _extract_key(mail.outbox[-1].body, "verify-email")
    verify_response = client.post(
        "/_allauth/browser/v1/auth/email/verify",
        {"key": key},
        content_type="application/json",
    )
    assert verify_response.status_code == 200, verify_response.json()

    address.refresh_from_db()
    assert address.verified is True


def test_signup_sends_a_verification_email() -> None:
    from django.test import Client

    client = Client()

    response = client.post(
        "/_allauth/browser/v1/auth/signup",
        {"email": "ada@example.com", "password": "s3cret-pass-1"},
        content_type="application/json",
    )

    assert response.status_code == 401
    body = response.json()
    flow_ids = {flow["id"] for flow in body["data"]["flows"]}
    assert "verify_email" in flow_ids
    assert len(mail.outbox) == 1
    assert "verify-email" in mail.outbox[0].body


def test_signing_up_with_an_existing_address_is_indistinguishable_from_a_new_one() -> None:
    """allauth's enumeration prevention answers a duplicate signup the
    same way as a fresh one and mails the existing account instead.
    Building that mail calls get_signup_url(), which needs
    HEADLESS_FRONTEND_URLS['account_signup'] — without it the response is
    a 500, which leaks exactly the fact the flow exists to hide. Found on
    a live deploy, not by this suite, because nothing here signed up
    twice with one address."""
    from django.test import Client

    client = Client()
    payload = {"email": "ada@example.com", "password": "s3cret-pass-1"}
    first = client.post(
        "/_allauth/browser/v1/auth/signup", payload, content_type="application/json"
    )
    assert first.status_code == 401, first.json()

    mail.outbox.clear()
    second = Client().post(
        "/_allauth/browser/v1/auth/signup", payload, content_type="application/json"
    )

    assert second.status_code == first.status_code, second.content
    assert len(mail.outbox) == 1
    subject = mail.outbox[0].subject.lower()
    assert "already" in subject or "account" in subject


def test_verifying_the_emailed_key_then_login_authenticates_the_session() -> None:
    from django.test import Client

    client = Client()
    _signup_and_verify(client, "ada@example.com", "s3cret-pass-1")
    # Verifying already authenticated this client (see _signup_and_verify) —
    # log out so the /login call below exercises a fresh credentials-based
    # login rather than 409ing on an already-authenticated session.
    client.logout()

    response = client.post(
        "/_allauth/browser/v1/auth/login",
        {"email": "ada@example.com", "password": "s3cret-pass-1"},
        content_type="application/json",
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["meta"]["is_authenticated"] is True
    assert body["data"]["user"]["email"] == "ada@example.com"

    session_response = client.get("/_allauth/browser/v1/auth/session")
    assert session_response.status_code == 200
    assert session_response.json()["meta"]["is_authenticated"] is True


def test_login_before_verification_is_rejected() -> None:
    from django.test import Client

    client = Client()
    client.post(
        "/_allauth/browser/v1/auth/signup",
        {"email": "ada@example.com", "password": "s3cret-pass-1"},
        content_type="application/json",
    )

    response = client.post(
        "/_allauth/browser/v1/auth/login",
        {"email": "ada@example.com", "password": "s3cret-pass-1"},
        content_type="application/json",
    )

    assert response.status_code in (400, 401)


def test_logout_ends_the_authenticated_session() -> None:
    from django.test import Client

    client = Client()
    _signup_and_verify(client, "ada@example.com", "s3cret-pass-1")
    client.post(
        "/_allauth/browser/v1/auth/login",
        {"email": "ada@example.com", "password": "s3cret-pass-1"},
        content_type="application/json",
    )

    response = client.delete("/_allauth/browser/v1/auth/session")

    assert response.status_code == 401
    session_response = client.get("/_allauth/browser/v1/auth/session")
    assert session_response.json()["meta"]["is_authenticated"] is False


def test_password_reset_round_trip() -> None:
    from django.test import Client

    client = Client()
    _signup_and_verify(client, "ada@example.com", "old-password-1")

    request_response = client.post(
        "/_allauth/browser/v1/auth/password/request",
        {"email": "ada@example.com"},
        content_type="application/json",
    )
    assert request_response.status_code == 200, request_response.json()
    key = _extract_key(mail.outbox[-1].body, "reset-password")

    reset_response = client.post(
        "/_allauth/browser/v1/auth/password/reset",
        {"key": key, "password": "new-password-1"},
        content_type="application/json",
    )
    # Deterministic 200: ACCOUNT_LOGIN_ON_PASSWORD_RESET (config/settings/
    # base.py) means a successful reset authenticates the session as part
    # of the same call — log out before the explicit login calls below so
    # they exercise fresh credentials instead of 409ing on an
    # already-authenticated session.
    assert reset_response.status_code == 200, reset_response.json()
    client.logout()

    old_login = client.post(
        "/_allauth/browser/v1/auth/login",
        {"email": "ada@example.com", "password": "old-password-1"},
        content_type="application/json",
    )
    assert old_login.status_code == 400

    new_login = client.post(
        "/_allauth/browser/v1/auth/login",
        {"email": "ada@example.com", "password": "new-password-1"},
        content_type="application/json",
    )
    assert new_login.status_code == 200, new_login.json()


def test_session_cookie_attributes() -> None:
    """Assert the cookie attributes on the actual Set-Cookie header, not the
    settings that produced them — this is the PRD §10 risk made concrete."""
    from django.test import Client

    client = Client()
    _signup_and_verify(client, "ada@example.com", "s3cret-pass-1")
    client.logout()  # fresh login below, not a 409 on the verify-created session

    response = client.post(
        "/_allauth/browser/v1/auth/login",
        {"email": "ada@example.com", "password": "s3cret-pass-1"},
        content_type="application/json",
    )

    cookie = response.cookies["sessionid"]
    assert cookie["httponly"] is True
    assert cookie["secure"] is True  # DEBUG=False in test settings
    assert cookie["samesite"] == "Lax"


def test_session_cookie_is_scoped_to_the_registrable_domain_when_configured() -> None:
    """PRD §4: Domain=.acme.com so acme.com and api.acme.com share the
    cookie. Asserted on the actual header with a production-shaped
    KEEL_APP_DOMAIN, not the host-only default local dev uses."""
    from django.test import Client, override_settings

    with override_settings(SESSION_COOKIE_DOMAIN=".acme.com"):
        client = Client()
        _signup_and_verify(client, "ada@example.com", "s3cret-pass-1")
        client.logout()  # fresh login below, not a 409 on the verify-created session

        response = client.post(
            "/_allauth/browser/v1/auth/login",
            {"email": "ada@example.com", "password": "s3cret-pass-1"},
            content_type="application/json",
        )

    assert response.cookies["sessionid"]["domain"] == ".acme.com"


def test_csrf_cookie_is_set_on_a_browser_client_get() -> None:
    from django.test import Client

    client = Client(enforce_csrf_checks=True)

    response = client.get("/_allauth/browser/v1/auth/session")

    assert response.status_code == 401
    assert "csrftoken" in response.cookies


def test_unsafe_request_without_csrf_header_is_rejected() -> None:
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.get("/_allauth/browser/v1/auth/session")

    response = client.post(
        "/_allauth/browser/v1/auth/login",
        {"email": "nobody@example.com", "password": "whatever"},
        content_type="application/json",
    )

    assert response.status_code == 403


def test_google_oauth_token_login_creates_a_user_and_authenticates() -> None:
    """Mocks the provider at allauth's adapter layer (PRD §8):
    GoogleProvider.verify_token is what would call out to Google to decode
    a real id_token — patched here so no network call happens, while the
    rest of allauth's social-login pipeline (SocialLogin construction,
    user + SocialAccount creation, session authentication) runs for real.
    """
    from unittest.mock import patch

    from allauth.socialaccount.providers.google.provider import GoogleProvider

    def fake_verify_token(self, request, token):
        identity_data = {
            "sub": "google-uid-123",
            "email": "grace@example.com",
            "email_verified": True,
            "name": "Grace Hopper",
        }
        return self.sociallogin_from_response(request, identity_data)

    client = Client()

    with patch.object(GoogleProvider, "verify_token", fake_verify_token):
        response = client.post(
            "/_allauth/browser/v1/auth/provider/token",
            {
                "provider": "google",
                "process": "login",
                "token": {"client_id": "", "id_token": "fake-jwt-not-verified"},
            },
            content_type="application/json",
        )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["meta"]["is_authenticated"] is True
    assert body["data"]["user"]["email"] == "grace@example.com"

    from keel.accounts.models import User

    assert User.objects.filter(email="grace@example.com").exists()

    session_response = client.get("/_allauth/browser/v1/auth/session")
    assert session_response.json()["meta"]["is_authenticated"] is True


def test_session_listing_and_revocation() -> None:
    client = Client()
    _signup_and_verify(client, "ada@example.com", "s3cret-pass-1")
    client.post(
        "/_allauth/browser/v1/auth/login",
        {"email": "ada@example.com", "password": "s3cret-pass-1"},
        content_type="application/json",
    )

    list_response = client.get("/_allauth/browser/v1/auth/sessions")
    assert list_response.status_code == 200, list_response.json()
    sessions = list_response.json()["data"]
    assert len(sessions) == 1
    current = sessions[0]
    assert current["is_current"] is True

    # Revoking your own current session ends it as part of the same
    # request — the response itself reports the now-unauthenticated state
    # (401), not a 200 confirming a revoke of some other session.
    revoke_response = client.delete(
        "/_allauth/browser/v1/auth/sessions",
        data={"sessions": [current["id"]]},
        content_type="application/json",
    )
    assert revoke_response.status_code == 401, revoke_response.json()
    assert revoke_response.json()["meta"]["is_authenticated"] is False

    session_response = client.get("/_allauth/browser/v1/auth/session")
    assert session_response.json()["meta"]["is_authenticated"] is False


def test_401_response_from_an_api_route_matches_the_phase_1_error_envelope() -> None:
    """Not an allauth endpoint — a real, protected /api/v1/ route,
    proving keel/core/exceptions.py's envelope (PRD §7) is what an
    unauthenticated request to this project's own API surface gets, as
    distinct from allauth's {status,data,meta} shape (see
    docs/auth-client-contract.md)."""
    client = Client()
    response = client.get("/api/v1/orgs/")

    assert response.status_code == 401, response.content
    body = response.json()
    assert body["error"]["code"] == "not_authenticated"
    assert "message" in body["error"]
