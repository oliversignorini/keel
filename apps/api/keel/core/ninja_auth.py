"""Session authentication for Ninja routes (PRD §7's error table).

Deny by default (PRD §4 task 1.12): every ``KeelAPI`` operation is mounted
through one of ``keel.core.ninja_authz``'s router constructors
(``keel_router`` / ``public_router`` / ``optional_auth_router``), each of
which declares its auth explicitly — there is no bare ``Router()`` with an
implicit default anywhere in the app routers. An operation that forgot to
go through one of those constructors is a bug caught by
``keel/core/tests/test_ninja_wiring.py``, not a silently-open endpoint.

Anonymous request → 401 ``not_authenticated``. Authenticated session
present but the request is an unsafe method (POST/PUT/PATCH/DELETE)
without a valid CSRF token → 401 ``authentication_failed`` — the same
outcome DRF's ``SessionAuthentication.enforce_csrf`` produces (via
``AuthenticationFailed``), not the 403 Django's own CSRF middleware would
give a plain view. Reproducing that exact mapping is why this hand-rolls
the CSRF check with ``CsrfViewMiddleware`` rather than turning on Ninja's
built-in ``csrf=True`` handling, which answers 403.

Rate limiting is a separate layer (``keel.core.ninja_throttle.
ThrottleMiddleware``) that runs ahead of routing for every ``/api/v1/``
request — not part of either callable below, so it applies uniformly to
routes built with ``public_router()``/``optional_auth_router()`` too,
which never call into this module at all.
"""

from django.http import HttpRequest
from django.middleware.csrf import CsrfViewMiddleware

from keel.core.exceptions import AuthenticationFailed, NotAuthenticated

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class _CSRFCheck(CsrfViewMiddleware):
    """Same trick DRF's own ``SessionAuthentication.enforce_csrf`` uses:
    reuse Django's CSRF middleware's checking logic without a response
    middleware chain to call it in, by capturing the rejection reason
    ``process_view`` would otherwise turn into an ``HttpResponseForbidden``.
    """

    def _reject(self, request: HttpRequest, reason: str) -> str:
        return reason


def enforce_csrf(request: HttpRequest) -> None:
    # Django's middleware machinery expects a real get_response/view_func
    # callable; neither is ever invoked here — process_view() only reads
    # the request and either returns a rejection reason or None. Same
    # dummy-callable trick DRF's own enforce_csrf uses.
    check = _CSRFCheck(get_response=lambda r: None)  # type: ignore[arg-type]
    check.process_request(request)
    reason = check.process_view(request, None, (), {})  # type: ignore[arg-type]
    if reason:
        raise AuthenticationFailed(details={"reason": f"CSRF Failed: {reason}"})


def session_auth(request: HttpRequest) -> object:
    """The one auth callable every ``keel_router()`` operation uses unless
    it is explicitly public (``optional_session_auth`` below, or a
    ``public_router()``/``keel.core.ninja_authz``).

    Returns the authenticated user (so Ninja's ``request.auth`` is
    populated) or raises — never returns ``None``, which Ninja would
    otherwise turn into its own generic 401 envelope instead of ours."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        raise NotAuthenticated()
    if request.method not in _SAFE_METHODS:
        enforce_csrf(request)
    return user


def optional_session_auth(request: HttpRequest) -> object:
    """For the rare operation that must work signed-out (PRD §6
    "Invitation": ``InvitationAcceptView.get`` needs org name + locked
    email to drive signup before there's a session). Never raises; always
    returns a user object (possibly ``AnonymousUser``) so
    ``request.auth.is_authenticated`` is always safe to read. A
    write on an authenticated session still gets the CSRF check."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and request.method not in _SAFE_METHODS:
        enforce_csrf(request)
    return user
