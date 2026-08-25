"""DRF's ``SessionAuthentication`` deliberately returns no
``WWW-Authenticate`` challenge (``authenticate_header`` is ``None``), and
``APIView.handle_exception`` coerces ``NotAuthenticated``/
``AuthenticationFailed`` to a 403 whenever no challenge is available —
documented DRF behavior, not a bug in DRF. Left as the default, every
protected endpoint in this project would answer an anonymous request with
403 rather than the 401 PRD §7's error table requires ("No session, or
session expired"). Supplying a header value is the documented fix.
"""

from rest_framework.authentication import SessionAuthentication as _SessionAuthentication


class SessionAuthentication(_SessionAuthentication):
    def authenticate_header(self, request: object) -> str:
        return "Session"
