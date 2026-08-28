"""Tests every row of PRD §7's error-envelope table against the shape,
not only the status code — a shallow test would assert status only.

Two halves. The first drives a fixture Ninja API (mounted on a test-only
URLconf, the same trick
``keel/organizations/tests/ninja_tenant_isolation_fixtures.py`` uses) so
the envelope is asserted as it actually reaches a client, through
``keel.core.ninja_exceptions``. The second asserts the exception classes'
own ``status_code`` / ``code`` / ``message`` vocabulary directly, since
that is what every call site constructs.
"""

from typing import Any

import pytest
from django.http import Http404
from django.urls import path
from ninja import NinjaAPI, Schema

from keel.core import exceptions as keel_exceptions
from keel.core import ninja_exceptions
from keel.core.exceptions import (
    AuthenticationFailed,
    Conflict,
    DomainError,
    NotAuthenticated,
    PaymentRequired,
    PermissionDeniedWithReason,
    Throttled,
    UnprocessableEntity,
)

# --- Fixture API: the envelope as a client actually receives it ----------

fixture_api = NinjaAPI(title="Keel API (error-envelope fixture)", version="fixture")
ninja_exceptions.register(fixture_api)


class _Payload(Schema):
    email: str


@fixture_api.post("/validation/")
def _validation(request: Any, payload: _Payload) -> dict:
    return {"ok": True}


@fixture_api.get("/not-found/")
def _not_found(request: Any) -> dict:
    raise Http404


@fixture_api.get("/raise/{kind}/")
def _raise(request: Any, kind: str) -> dict:
    raise _RAISERS[kind]()


_RAISERS: dict[str, Any] = {
    "not_authenticated": NotAuthenticated,
    "authentication_failed": AuthenticationFailed,
    "payment_required": lambda: PaymentRequired(
        code="SEAT_LIMIT_EXCEEDED",
        message="This plan includes 10 seats. Upgrade to add more.",
        details=[{"field": "seats", "message": "Limit reached."}],
    ),
    "permission_denied": lambda: PermissionDeniedWithReason(
        code="insufficient_role",
        message="You do not have permission to perform this action.",
        denial={"required": "org.update"},
    ),
    "conflict": lambda: Conflict(code="already_accepted", message="Invitation already accepted."),
    "unprocessable": lambda: UnprocessableEntity(
        code="invalid_state_transition", message="Job is already finished."
    ),
    "throttled": lambda: Throttled(wait=30),
    "domain_error": DomainError,
}

urlpatterns = [path("api/v1/", fixture_api.urls)]

pytestmark = pytest.mark.urls(__name__)


def test_400_validation_error_names_the_offending_field(client) -> None:
    response = client.post("/api/v1/validation/", {}, content_type="application/json")

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert {row["field"] for row in body["error"]["details"]} == {"email"}


def test_401_not_authenticated(client) -> None:
    response = client.get("/api/v1/raise/not_authenticated/")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
    assert response.json()["error"]["message"]


def test_401_authentication_failed(client) -> None:
    response = client.get("/api/v1/raise/authentication_failed/")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


def test_402_payment_required(client) -> None:
    response = client.get("/api/v1/raise/payment_required/")

    assert response.status_code == 402
    body = response.json()
    assert body["error"]["code"] == "SEAT_LIMIT_EXCEEDED"
    assert body["error"]["message"] == "This plan includes 10 seats. Upgrade to add more."
    assert body["error"]["details"] == [{"field": "seats", "message": "Limit reached."}]


def test_403_permission_denied_carries_decision_reason_and_denial_context(client) -> None:
    """§4 invariant 2 / §7: code carries Decision.reason, the sibling
    ``denial`` key carries Decision.details (api-patterns finding 17 —
    ``details`` stays list[{field, message}] | None everywhere, including
    here)."""
    response = client.get("/api/v1/raise/permission_denied/")

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "insufficient_role"
    assert body["error"]["details"] is None
    assert body["error"]["denial"] == {"required": "org.update"}


def test_404_not_found(client) -> None:
    response = client.get("/api/v1/not-found/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_409_conflict(client) -> None:
    response = client.get("/api/v1/raise/conflict/")

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "already_accepted"
    assert body["error"]["message"] == "Invitation already accepted."


def test_422_unprocessable_entity(client) -> None:
    response = client.get("/api/v1/raise/unprocessable/")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_state_transition"


def test_429_throttled_sets_retry_after_header(client) -> None:
    response = client.get("/api/v1/raise/throttled/")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json()["error"]["code"] == "throttled"


def test_bare_domain_error_uses_its_own_defaults(client) -> None:
    response = client.get("/api/v1/raise/domain_error/")

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "domain_error"
    assert body["error"]["message"] == "A domain error occurred."
    assert body["error"]["details"] is None


# --- The vocabulary itself ------------------------------------------------


def test_keel_not_authenticated_shape() -> None:
    exc = keel_exceptions.NotAuthenticated()

    assert exc.status_code == 401
    assert exc.code == "not_authenticated"
    assert exc.message == "Authentication credentials were not provided."


def test_keel_authentication_failed_shape() -> None:
    exc = keel_exceptions.AuthenticationFailed()

    assert exc.status_code == 401
    assert exc.code == "authentication_failed"
    assert exc.message == "Incorrect authentication credentials."


def test_domain_error_is_a_plain_exception_carrying_its_message() -> None:
    """No DRF ``APIException`` underneath any more (phase-10 DRF removal):
    a ``DomainError`` is an ordinary exception whose ``str()`` is its
    human message, and ``keel.core.ninja_exceptions`` is the only thing
    that turns it into a response."""
    exc = Conflict(code="already_accepted", message="Invitation already accepted.")

    assert isinstance(exc, Exception)
    assert str(exc) == "Invitation already accepted."


def test_keel_throttled_without_a_wait_uses_the_default_message() -> None:
    """keel.core.ninja_throttle only ever raises with wait= set; this
    proves the no-wait branch still produces a sane envelope."""
    exc = keel_exceptions.Throttled()

    assert exc.wait is None
    assert exc.status_code == 429
    assert exc.code == "throttled"
    assert exc.message == "Request was throttled."
    assert exc.response_headers == {}


def test_keel_throttled_with_a_wait_exposes_a_retry_after_header() -> None:
    exc = keel_exceptions.Throttled(wait=12.5)

    assert exc.response_headers == {"Retry-After": "12"}


def test_a_plain_domain_error_has_no_response_headers() -> None:
    assert keel_exceptions.DomainError().response_headers == {}


def test_a_plain_domain_error_has_no_extra_envelope_fields() -> None:
    assert keel_exceptions.DomainError().extra_envelope_fields == {}


def test_throttled_carries_extra_headers_alongside_retry_after() -> None:
    exc = keel_exceptions.Throttled(
        wait=12.5,
        headers={
            "X-RateLimit-Limit": "300",
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "1700000000",
        },
    )

    assert exc.response_headers == {
        "Retry-After": "12",
        "X-RateLimit-Limit": "300",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "1700000000",
    }


def test_permission_denied_with_reason_carries_denial_in_extra_envelope_fields() -> None:
    exc = PermissionDeniedWithReason(code="insufficient_role", denial={"required": "org.update"})

    assert exc.details is None
    assert exc.extra_envelope_fields == {"denial": {"required": "org.update"}}


def test_keel_throttled_with_a_wait_pluralizes_correctly() -> None:
    singular = keel_exceptions.Throttled(wait=1)
    plural = keel_exceptions.Throttled(wait=30)

    assert "1 second." in singular.message
    assert "30 seconds." in plural.message
