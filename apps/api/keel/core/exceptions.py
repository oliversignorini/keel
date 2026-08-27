"""Domain exception hierarchy and the DRF exception handler producing the
error envelope specified in PRD §7:

    { "error": { "code": ..., "message": ..., "details": [...] } }

Every status code in that section's table maps here: 400 (serializer
ValidationError), 401 (NotAuthenticated / AuthenticationFailed), 402
(PaymentRequired), 403 (PermissionDeniedWithReason — carries
Decision.reason / Decision.details, PRD §4 invariant 2), 404 (NotFound),
409 (Conflict), 422 (UnprocessableEntity), 429 (Throttled, with
Retry-After — set by DRF's own default handler, preserved here).
"""

from typing import Any

from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class DomainError(drf_exceptions.APIException):
    """Base for exceptions carrying an explicit machine-readable code,
    human message, and structured details — the vocabulary the error
    envelope is built from."""

    status_code = 400
    default_code = "domain_error"
    default_message = "A domain error occurred."

    def __init__(
        self,
        code: str | None = None,
        message: str | None = None,
        details: list[dict[str, Any]] | dict[str, Any] | None = None,
    ) -> None:
        self.code = code or self.default_code
        self.message = message or self.default_message
        self.details = details
        super().__init__(detail=self.message, code=self.code)


class NotAuthenticated(DomainError):
    """Framework-independent counterpart to DRF's own ``NotAuthenticated``
    (used by ``keel.core.ninja_auth``, PRD §7: anonymous request to a
    protected route answers 401, never 403)."""

    status_code = 401
    default_code = "not_authenticated"
    default_message = "Authentication credentials were not provided."


class AuthenticationFailed(DomainError):
    """Framework-independent counterpart to DRF's own ``AuthenticationFailed``
    — used by ``keel.core.ninja_auth`` for a CSRF failure on an
    otherwise-authenticated session, matching
    ``keel.core.authentication.SessionAuthentication``'s 401 behaviour."""

    status_code = 401
    default_code = "authentication_failed"
    default_message = "Incorrect authentication credentials."


class PaymentRequired(DomainError):
    status_code = 402
    default_code = "payment_required"
    default_message = "Plan lacks the feature or the limit is reached."


class PermissionDeniedWithReason(DomainError):
    status_code = 403
    default_code = "permission_denied"
    default_message = "You do not have permission to perform this action."


class Conflict(DomainError):
    status_code = 409
    default_code = "conflict"
    default_message = "A domain invariant was violated."


class UnprocessableEntity(DomainError):
    status_code = 422
    default_code = "unprocessable_entity"
    default_message = "Semantically invalid but well-formed."


class Throttled(DomainError):
    """Framework-independent counterpart to DRF's own ``Throttled`` — used
    by ``keel.core.ninja_throttle``. ``wait`` is the number of seconds the
    caller should wait, surfaced as the ``Retry-After`` header by the
    Ninja exception handler (``keel.core.ninja_exceptions``)."""

    status_code = 429
    default_code = "throttled"
    default_message = "Request was throttled."

    def __init__(self, wait: float | None = None, details: Any = None) -> None:
        self.wait = wait
        if wait is not None:
            unit = "second" if int(wait) == 1 else "seconds"
            message = f"{self.default_message} Expected available in {int(wait)} {unit}."
        else:
            message = self.default_message
        super().__init__(code=self.default_code, message=message, details=details)


def _validation_details(detail: Any) -> list[dict[str, Any]]:
    if isinstance(detail, dict):
        results = []
        for field, errors in detail.items():
            errors_list = errors if isinstance(errors, list) else [errors]
            for error in errors_list:
                results.append({"field": field, "message": str(error)})
        return results
    if isinstance(detail, list):
        return [{"field": None, "message": str(error)} for error in detail]
    return [{"field": None, "message": str(detail)}]


def _envelope_parts(exc: Exception) -> tuple[str, str, Any]:
    if isinstance(exc, DomainError):
        return exc.code, exc.message, exc.details

    if isinstance(exc, drf_exceptions.ValidationError):
        return "validation_error", "Validation failed.", _validation_details(exc.detail)

    if isinstance(exc, drf_exceptions.APIException):
        code = str(exc.get_codes()) if not isinstance(exc.get_codes(), str) else exc.get_codes()
        message = str(exc.detail)
        return code, message, None

    return "error", str(exc), None


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    code, message, details = _envelope_parts(exc)
    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response
