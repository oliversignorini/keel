from django.test import RequestFactory

from keel.core.authentication import SessionAuthentication


def test_authenticate_header_is_non_empty() -> None:
    """A non-empty header is what stops DRF coercing 401 to 403 for an
    unauthenticated request (see the module docstring)."""
    auth = SessionAuthentication()
    request = RequestFactory().get("/")

    assert auth.authenticate_header(request) == "Session"
