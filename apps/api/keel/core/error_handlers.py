"""Ninja exception handlers producing the error envelope PRD §7
specifies:

    { "error": { "code": ..., "message": ..., "details": [...] } }

Registered once, on the single ``KeelAPI`` instance
(``keel/core/api.py``), via ``register(api)``.
"""

from typing import Any

from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from ninja import NinjaAPI, Schema
from ninja.errors import ValidationError as NinjaValidationError

from keel.core.exceptions import DomainError


class ErrorBodyOut(Schema):
    code: str
    message: str
    details: Any = None


class ErrorEnvelope(Schema):
    """PRD §7's error shape as a published Ninja schema — the response
    every ``keel.core.authz`` router constructor attaches to the
    project's default error-response set ({400, 401, 403, 404, 409, 422,
    429}) on every operation, so the OpenAPI document (and the generated
    TypeScript client) describes the envelope this module actually
    produces instead of leaving every error typed ``unknown``."""

    error: ErrorBodyOut


def _validation_details(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ninja's ``ValidationError.errors`` is a list of pydantic-derived
    dicts, each with a ``loc`` tuple whose first element names the
    parameter source (``body`` / ``query`` / ``path`` / ...) and the rest
    the field path. Reshape to the flat ``{field, message}`` list PRD §7's
    envelope specifies."""
    details = []
    for error in errors:
        loc = error.get("loc", ())
        # loc is (source, *schema_param_name_and_field_path) — e.g.
        # ("body", "payload", "name"). The leaf is the actual field name;
        # everything before it is Ninja's own plumbing (the parameter
        # source, then the schema parameter's own name), which DRF's flat
        # {field, message} shape has no equivalent of.
        field = str(loc[-1]) if loc else None
        details.append({"field": field, "message": error.get("msg", str(error))})
    return details


def _envelope(status_code: int, code: str, message: str, details: Any) -> HttpResponse:
    return JsonResponse(
        {"error": {"code": code, "message": message, "details": details}}, status=status_code
    )


def domain_error_response(exc: DomainError) -> HttpResponse:
    """Render a ``DomainError`` as PRD §7's envelope. Shared by the Ninja
    exception handler below and ``keel.core.throttle.ThrottleMiddleware``,
    which raises/catches ``Throttled`` outside Ninja's own dispatch."""
    response = _envelope(exc.status_code, exc.code, exc.message, exc.details)
    for header, value in exc.response_headers.items():
        response[header] = value
    return response


def register(api: NinjaAPI) -> None:
    @api.exception_handler(DomainError)
    def _domain_error(request: HttpRequest, exc: DomainError) -> HttpResponse:
        return domain_error_response(exc)

    @api.exception_handler(Http404)
    def _not_found(request: HttpRequest, exc: Http404) -> HttpResponse:
        return _envelope(404, "not_found", str(exc) or "Not found.", None)

    @api.exception_handler(NinjaValidationError)
    def _validation_error(request: HttpRequest, exc: NinjaValidationError) -> HttpResponse:
        details = _validation_details(exc.errors)
        return _envelope(400, "validation_error", "Validation failed.", details)
