"""Ninja exception handlers producing the error envelope PRD §7
specifies:

    { "error": { "code": ..., "message": ..., "details": [...] } }

Registered once, on the single ``KeelAPI`` instance
(``keel/core/ninja_api.py``), via ``register(api)``.
"""

from typing import Any

from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from ninja import NinjaAPI
from ninja.errors import ValidationError as NinjaValidationError

from keel.core.exceptions import DomainError


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


def register(api: NinjaAPI) -> None:
    @api.exception_handler(DomainError)
    def _domain_error(request: HttpRequest, exc: DomainError) -> HttpResponse:
        response = _envelope(exc.status_code, exc.code, exc.message, exc.details)
        wait = getattr(exc, "wait", None)
        if wait is not None:
            response["Retry-After"] = f"{int(wait)}"
        return response

    @api.exception_handler(Http404)
    def _not_found(request: HttpRequest, exc: Http404) -> HttpResponse:
        return _envelope(404, "not_found", str(exc) or "Not found.", None)

    @api.exception_handler(NinjaValidationError)
    def _validation_error(request: HttpRequest, exc: NinjaValidationError) -> HttpResponse:
        details = _validation_details(exc.errors)
        return _envelope(400, "validation_error", "Validation failed.", details)
