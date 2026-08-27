"""``keel.core.ninja_auth`` — the deny-by-default session auth every
``KeelAPI`` operation declares (PRD §4 task 1.12, PRD §7's error table).

The two rules worth proving, and the reason this file exists rather than
leaning on the endpoint tests: an anonymous request to a protected route
answers **401 not_authenticated** (never 403), and an authenticated
session making an unsafe request without a valid CSRF token answers **401
authentication_failed** — not the 403 Django's own CSRF middleware would
give a plain view, and not a silent pass. Both are asserted end to end
against real, production Ninja routes on the real URLconf, so a change to
``keel_router``'s wiring cannot make them vacuous.
"""

from typing import Any

import pytest
from django.test import Client, RequestFactory

from keel.accounts.models import User
from keel.core.exceptions import AuthenticationFailed, NotAuthenticated
from keel.core.ninja_auth import enforce_csrf, optional_session_auth, session_auth

pytestmark = pytest.mark.django_db


def _csrf_client() -> Client:
    """``enforce_csrf_checks=True`` is what makes these tests meaningful:
    Django's test client otherwise marks every request CSRF-exempt."""
    return Client(enforce_csrf_checks=True)


def _user(email: str = "ninja-auth@example.com") -> User:
    return User.objects.create_user(email=email, password="s3cret-pass")


# --- End to end, against production routes -------------------------------


def test_anonymous_request_to_a_protected_route_is_401_not_403() -> None:
    response = Client().get("/api/v1/orgs/")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_write_without_a_csrf_token_is_401_authentication_failed() -> None:
    """The gap this file closes: a logged-in session POSTing without the
    CSRF header must get 401 ``authentication_failed`` from
    ``session_auth`` -> ``enforce_csrf``, not a 403 and not a 201."""
    client = _csrf_client()
    client.force_login(_user())

    response = client.post(
        "/api/v1/orgs/",
        {"name": "Acme", "slug": "acme-csrf"},
        content_type="application/json",
    )

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "authentication_failed"
    assert "CSRF" in body["error"]["details"]["reason"]


def test_write_with_a_valid_csrf_token_is_allowed_through() -> None:
    """The other half of the same rule — otherwise the test above would
    also pass with a ``session_auth`` that rejects every write."""
    client = _csrf_client()
    client.force_login(_user("csrf-ok@example.com"))
    # Django accepts any well-formed 64-character token as long as the
    # cookie and the header unmask to the same secret — which identical
    # values trivially do. Cheaper and less brittle than driving a real
    # @ensure_csrf_cookie view to seed the cookie first.
    token = "a" * 64
    client.cookies["csrftoken"] = token

    response = client.post(
        "/api/v1/orgs/",
        {"name": "Acme", "slug": "acme-csrf-ok"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert response.status_code == 201, response.content


def test_safe_method_on_an_authenticated_session_skips_the_csrf_check() -> None:
    client = _csrf_client()
    client.force_login(_user("safe-method@example.com"))

    response = client.get("/api/v1/orgs/")

    assert response.status_code == 200


def test_optional_session_auth_route_works_signed_out() -> None:
    """``GET /invite/<token>/`` is the one route that must answer without
    a session (phase-3.md B.4) — it reaches its own handler rather than
    ``session_auth``'s 401."""
    response = Client().get("/api/v1/invite/no-such-token/")

    assert response.status_code != 401


# --- The callables directly ----------------------------------------------


def test_session_auth_raises_not_authenticated_for_an_anonymous_request() -> None:
    request = RequestFactory().get("/api/v1/orgs/")

    with pytest.raises(NotAuthenticated):
        session_auth(request)


def test_session_auth_raises_not_authenticated_when_no_user_is_attached() -> None:
    """No ``AuthenticationMiddleware`` in front (a bare request object) is
    a missing session, not a crash."""
    request = RequestFactory().get("/api/v1/orgs/")
    assert not hasattr(request, "user")

    with pytest.raises(NotAuthenticated):
        session_auth(request)


def test_session_auth_returns_the_user_on_a_safe_method() -> None:
    user = _user("returns-user@example.com")
    request = RequestFactory().get("/api/v1/orgs/")
    request.user = user  # type: ignore[attr-defined]

    assert session_auth(request) is user


def test_enforce_csrf_raises_authentication_failed_without_a_token() -> None:
    request = RequestFactory().post("/api/v1/orgs/")

    with pytest.raises(AuthenticationFailed) as excinfo:
        enforce_csrf(request)

    exc = excinfo.value
    assert exc.status_code == 401
    assert exc.code == "authentication_failed"
    details: Any = exc.details
    assert "CSRF Failed" in details["reason"]


def test_optional_session_auth_returns_anonymous_user_untouched() -> None:
    from django.contrib.auth.models import AnonymousUser

    request = RequestFactory().get("/api/v1/invite/tok/")
    anonymous = AnonymousUser()
    request.user = anonymous  # type: ignore[attr-defined]

    assert optional_session_auth(request) is anonymous


def test_optional_session_auth_still_enforces_csrf_on_an_authenticated_write() -> None:
    user = _user("optional-write@example.com")
    request: Any = RequestFactory().post("/api/v1/invite/tok/")
    request.user = user

    with pytest.raises(AuthenticationFailed):
        optional_session_auth(request)
