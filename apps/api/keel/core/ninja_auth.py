"""Session authentication for Ninja routes (PRD §7's error table;
``keel/core/authentication.py``'s docstring, kept for the DRF views that
still exist during the migration, explains the 401-vs-403 distinction this
preserves).

Deny by default (PRD §4 task 1.12): every ``KeelAPI`` operation must pass
``auth=session_auth`` explicitly — there is no global default, so an
operation that forgets it is a bug caught by ``keel/core/tests/
test_ninja_wiring.py``, not a silently-open endpoint.

Anonymous request → 401 ``not_authenticated``. Authenticated session
present but the request is an unsafe method (POST/PUT/PATCH/DELETE)
without a valid CSRF token → 401 ``authentication_failed`` — the same
outcome DRF's ``SessionAuthentication.enforce_csrf`` produces (via
``AuthenticationFailed``), not the 403 Django's own CSRF middleware would
give a plain view. Reproducing that exact mapping is why this hand-rolls
the CSRF check with ``CsrfViewMiddleware`` rather than turning on Ninja's
built-in ``csrf=True`` handling, which answers 403.
"""

from django.http import HttpRequest
from django.middleware.csrf import CsrfViewMiddleware

from keel.core.exceptions import AuthenticationFailed, NotAuthenticated
from keel.core.ninja_throttle import throttle

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
    """The one auth callable every ``KeelAPI`` operation must declare
    unless it is explicitly public (``optional_session_auth`` below).
    General rate limiting (PRD §3 NFR "Security") runs here too, ahead of
    the auth check, so it applies uniformly regardless of whether the
    request turns out to be authenticated.

    Returns the authenticated user (so Ninja's ``request.auth`` is
    populated) or raises — never returns ``None``, which Ninja would
    otherwise turn into its own generic 401 envelope instead of ours."""
    throttle(request)
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
    throttle(request)
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and request.method not in _SAFE_METHODS:
        enforce_csrf(request)
    return user
