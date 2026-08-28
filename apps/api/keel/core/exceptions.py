"""Domain exception hierarchy behind the error envelope specified in
PRD §7:

    { "error": { "code": ..., "message": ..., "details": [...] } }

Every status code in that section's table maps here: 400 (validation —
raised by Ninja itself and translated in ``keel.core.ninja_exceptions``),
401 (NotAuthenticated / AuthenticationFailed), 402 (PaymentRequired), 403
(PermissionDeniedWithReason — carries Decision.reason as ``code`` and
Decision.details as its own ``denial`` envelope key, PRD §4 invariant 2),
404 (Http404), 409 (Conflict), 422 (UnprocessableEntity), 429 (Throttled,
whose ``wait`` becomes the ``Retry-After`` header, plus the
``X-RateLimit-*`` headers ``keel.core.ninja_throttle`` computes).

These are framework-independent by design: they carry ``status_code`` /
``code`` / ``message`` / ``details`` and nothing else (``details`` is
always ``list[{field, message}] | None`` — api-patterns finding 17 — a
subclass that needs other structured context, like
``PermissionDeniedWithReason``, publishes it through
``extra_envelope_fields`` instead of overloading ``details`` with a
second shape), and ``keel.core.ninja_exceptions.register`` is the single
place that turns one into an HTTP response.
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

    @property
    def response_headers(self) -> dict[str, str]:
        """Extra headers the envelope handler should attach to the HTTP
        response, empty by default. ``Throttled`` overrides this instead
        of the handler reaching for ``getattr(exc, "wait", None)`` — a
        private fact about one subclass leaking into the one place that's
        supposed to render any ``DomainError`` uniformly (posd finding
        12)."""
        return {}

    @property
    def extra_envelope_fields(self) -> dict[str, Any]:
        """Additional top-level keys the envelope handler
        (``keel.core.ninja_exceptions.domain_error_response``) merges into
        the ``error`` object, sibling to ``details`` — empty by default.
        ``PermissionDeniedWithReason`` overrides this to carry structured
        denial context under its own ``denial`` key rather than overloading
        ``details``, which validation errors already use for a different
        shape (``list[{field, message}]``) — api-patterns finding 17."""
        return {}


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

    def __init__(
        self,
        code: str | None = None,
        message: str | None = None,
        denial: dict[str, Any] | None = None,
    ) -> None:
        # `details` stays None here — a permission denial has no per-field
        # validation errors, only the structured `denial` context below
        # (api-patterns finding 17: `details` is one shape, list[{field,
        # message}], everywhere; a 403's own context is a sibling key).
        super().__init__(code=code, message=message, details=None)
        self.denial = denial

    @property
    def extra_envelope_fields(self) -> dict[str, Any]:
        return {"denial": self.denial}


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

    def __init__(
        self,
        wait: float | None = None,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.wait = wait
        # api-patterns finding 7: the three X-RateLimit-* headers, computed
        # by keel.core.ninja_throttle.RateThrottle.check from the same
        # window state that decided this request was over-limit —
        # threaded through here so the 429 response carries them too, not
        # only successful throttled-scope responses.
        self._extra_headers = headers or {}
        if wait is not None:
            unit = "second" if int(wait) == 1 else "seconds"
            message = f"{self.default_message} Expected available in {int(wait)} {unit}."
        else:
            message = self.default_message
        super().__init__(code=self.default_code, message=message, details=details)

    @property
    def response_headers(self) -> dict[str, str]:
        headers = dict(self._extra_headers)
        if self.wait is not None:
            headers["Retry-After"] = f"{int(self.wait)}"
        return headers
