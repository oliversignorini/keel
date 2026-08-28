"""Request-id middleware (PRD §4, task 1.12): every request gets an id —
reused from an incoming ``X-Request-ID`` header, or generated — echoed on
the response and available to every log line via
``keel.core.logging.request_id_var`` for the duration of the request."""

import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from keel.core.logging import request_id_var


class RequestIDMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(request_id)
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token)


class ImpersonationMiddleware:
    """Resolves the impersonator (PRD §6 "Impersonation") once per
    request: ``request.impersonator`` is the staff ``User`` who
    started the session, or ``None`` for an ordinary session — the value
    every view below threads into an audited service call as
    ``impersonator=``. Also publishes the same value to
    ``keel.core.impersonation``'s contextvar for the rare code that isn't a
    view and doesn't have ``request`` — see that module's docstring."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        from keel.accounts.models import User
        from keel.core.impersonation import _current_impersonator_id, get_impersonator_id

        impersonator_id = get_impersonator_id(request)
        impersonator = User.objects.filter(pk=impersonator_id).first() if impersonator_id else None
        request.impersonator = impersonator  # type: ignore[attr-defined]
        token = _current_impersonator_id.set(impersonator_id)
        try:
            return self.get_response(request)
        finally:
            _current_impersonator_id.reset(token)
