"""Domain exception hierarchy behind the error envelope specified in
PRD §7:

    { "error": { "code": ..., "message": ..., "details": [...] } }

Every status code in that section's table maps here: 400 (validation —
raised by Ninja itself and translated in ``keel.core.ninja_exceptions``),
401 (NotAuthenticated / AuthenticationFailed), 402 (PaymentRequired), 403
(PermissionDeniedWithReason — carries Decision.reason / Decision.details,
PRD §4 invariant 2), 404 (Http404), 409 (Conflict), 422
(UnprocessableEntity), 429 (Throttled, whose ``wait`` becomes the
``Retry-After`` header).

These are framework-independent by design: they carry ``status_code`` /
``code`` / ``message`` / ``details`` and nothing else, and
``keel.core.ninja_exceptions.register`` is the single place that turns one
into an HTTP response.
"""

from typing import Any


class DomainError(Exception):
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
        super().__init__(self.message)


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
    otherwise-authenticated session: 401, not the 403 Django's own CSRF
    middleware would give a plain view (PRD §7)."""

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
