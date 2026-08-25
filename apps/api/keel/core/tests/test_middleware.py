from django.http import HttpResponse
from django.test import RequestFactory

from keel.core.logging import get_request_id
from keel.core.middleware import RequestIDMiddleware


def test_generates_a_request_id_when_none_supplied() -> None:
    seen = {}

    def get_response(request):
        seen["request_id_during_request"] = get_request_id()
        return HttpResponse()

    middleware = RequestIDMiddleware(get_response)
    request = RequestFactory().get("/")

    response = middleware(request)

    assert response["X-Request-ID"]
    assert seen["request_id_during_request"] == response["X-Request-ID"]


def test_reuses_the_incoming_x_request_id_header() -> None:
    def get_response(request):
        return HttpResponse()

    middleware = RequestIDMiddleware(get_response)
    request = RequestFactory().get("/", HTTP_X_REQUEST_ID="client-supplied-id")

    response = middleware(request)

    assert response["X-Request-ID"] == "client-supplied-id"


def test_request_id_is_cleared_after_the_request() -> None:
    def get_response(request):
        return HttpResponse()

    middleware = RequestIDMiddleware(get_response)
    request = RequestFactory().get("/")

    middleware(request)

    assert get_request_id() is None
