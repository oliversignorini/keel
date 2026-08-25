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
