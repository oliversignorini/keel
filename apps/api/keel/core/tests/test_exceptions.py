"""Tests every row of PRD §7's error-envelope table against the shape,
not only the status code — a shallow test would assert status only."""

from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    Throttled,
    ValidationError,
)

from keel.core import exceptions as keel_exceptions
from keel.core.exceptions import (
    Conflict,
    PaymentRequired,
    PermissionDeniedWithReason,
    UnprocessableEntity,
    _validation_details,
    exception_handler,
)


def envelope(response):
    return response.data


def test_400_validation_error_from_serializer() -> None:
    exc = ValidationError({"email": ["This field is required."]})

    response = exception_handler(exc, {})

    assert response is not None
    assert response.status_code == 400
    body = envelope(response)
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"] == [{"field": "email", "message": "This field is required."}]


def test_400_validation_error_with_non_field_errors_list() -> None:
    exc = ValidationError(["Top-level error not tied to a field."])

    response = exception_handler(exc, {})

    assert response is not None
    assert response.status_code == 400
    body = envelope(response)
    assert body["error"]["details"] == [
        {"field": None, "message": "Top-level error not tied to a field."}
    ]


def test_validation_details_wraps_a_bare_scalar_detail() -> None:
    assert _validation_details("just a string") == [{"field": None, "message": "just a string"}]


def test_401_not_authenticated() -> None:
    exc = NotAuthenticated()

    response = exception_handler(exc, {})

    assert response is not None
    assert response.status_code == 401
    body = envelope(response)
    assert body["error"]["code"] == "not_authenticated"
    assert "message" in body["error"]


def test_401_authentication_failed() -> None:
    exc = AuthenticationFailed()

    response = exception_handler(exc, {})

    assert response is not None
    assert response.status_code == 401
    assert envelope(response)["error"]["code"] == "authentication_failed"


def test_402_payment_required() -> None:
    exc = PaymentRequired(
        code="SEAT_LIMIT_EXCEEDED",
        message="This plan includes 10 seats. Upgrade to add more.",
        details=[{"field": "seats", "message": "Limit reached."}],
    )

    response = exception_handler(exc, {})

    assert response is not None
    assert response.status_code == 402
    body = envelope(response)
    assert body["error"]["code"] == "SEAT_LIMIT_EXCEEDED"
    assert body["error"]["message"] == "This plan includes 10 seats. Upgrade to add more."
    assert body["error"]["details"] == [{"field": "seats", "message": "Limit reached."}]


def test_403_permission_denied_carries_decision_reason_and_details() -> None:
    """§4 invariant 2 / §7: code carries Decision.reason, details carries Decision.details."""
    exc = PermissionDeniedWithReason(
        code="insufficient_role",
        message="You do not have permission to perform this action.",
        details={"required": "org.update"},
    )

    response = exception_handler(exc, {})

    assert response is not None
    assert response.status_code == 403
    body = envelope(response)
    assert body["error"]["code"] == "insufficient_role"
    assert body["error"]["details"] == {"required": "org.update"}


def test_404_not_found() -> None:
    exc = NotFound()

    response = exception_handler(exc, {})

    assert response is not None
    assert response.status_code == 404
    assert envelope(response)["error"]["code"] == "not_found"


def test_409_conflict() -> None:
    exc = Conflict(code="already_accepted", message="Invitation already accepted.")

    response = exception_handler(exc, {})

    assert response is not None
    assert response.status_code == 409
    body = envelope(response)
    assert body["error"]["code"] == "already_accepted"
    assert body["error"]["message"] == "Invitation already accepted."


def test_422_unprocessable_entity() -> None:
    exc = UnprocessableEntity(code="invalid_state_transition", message="Job is already finished.")

    response = exception_handler(exc, {})

    assert response is not None
    assert response.status_code == 422
    assert envelope(response)["error"]["code"] == "invalid_state_transition"


def test_429_throttled_sets_retry_after_header() -> None:
    exc = Throttled(wait=30)

    response = exception_handler(exc, {})

    assert response is not None
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert envelope(response)["error"]["code"] == "throttled"


def test_unhandled_exception_returns_none_for_django_default_handling() -> None:
    response = exception_handler(ValueError("boom"), {})

    assert response is None


def test_keel_not_authenticated_matches_drf_shape() -> None:
    """Framework-independent counterpart used by keel.core.ninja_auth —
    same code/status DRF's own NotAuthenticated produces."""
    exc = keel_exceptions.NotAuthenticated()

    assert exc.status_code == 401
    assert exc.code == "not_authenticated"
    assert exc.message == "Authentication credentials were not provided."


def test_keel_authentication_failed_matches_drf_shape() -> None:
    exc = keel_exceptions.AuthenticationFailed()

    assert exc.status_code == 401
    assert exc.code == "authentication_failed"
    assert exc.message == "Incorrect authentication credentials."


def test_keel_throttled_without_a_wait_uses_the_default_message() -> None:
    """keel.core.ninja_throttle only ever raises with wait= set; this
    proves the no-wait branch still produces a sane envelope."""
    exc = keel_exceptions.Throttled()

    assert exc.wait is None
    assert exc.status_code == 429
    assert exc.code == "throttled"
    assert exc.message == "Request was throttled."


def test_keel_throttled_with_a_wait_pluralizes_correctly() -> None:
    singular = keel_exceptions.Throttled(wait=1)
    plural = keel_exceptions.Throttled(wait=30)

    assert "1 second." in singular.message
    assert "30 seconds." in plural.message
