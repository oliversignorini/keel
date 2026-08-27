"""Rate limiting for Ninja routes (PRD §3 NFR "Security": "Rate limiting
... on the API generally"; docs/plans/phase-8.md 8.6).

Ported from Django REST Framework's ``SimpleRateThrottle`` /
``AnonRateThrottle`` / ``UserRateThrottle`` — same cache-backed sliding
window over Django's cache (Redis in production), same
``KEEL_API_THROTTLE_USER_RATE`` / ``_ANON_RATE`` settings, same 429 +
``Retry-After`` behaviour — with no dependency on that framework.

Applied as a layer over every ``/api/v1/`` request (``ThrottleMiddleware``
below), not tucked inside the deny-by-default auth callables
(``keel.core.ninja_auth``) — a request that arrived is what gets rate
limited, regardless of whether the route it hit turns out to require a
session. Auth-gated routes and the project's public routers
(``keel.core.ninja_authz.public_router`` — ``GET /plans/``, the Stripe
webhook) are covered identically because neither ever calls
``session_auth``/``optional_session_auth``, only routes through this
middleware.
"""

import time
from collections.abc import Callable

from django.conf import settings
from django.core.cache import cache as default_cache
from django.http import HttpRequest, HttpResponse

from keel.core.exceptions import Throttled

_PERIODS: dict[str, int] = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_rate(rate: str | None) -> tuple[int, int] | None:
    if rate is None:
        return None
    num, period = rate.split("/")
    return int(num), _PERIODS[period[0]]


def _get_ident(request: HttpRequest) -> str:
    xff = request.headers.get("x-forwarded-for")
    remote_addr: str = request.META.get("REMOTE_ADDR") or ""
    num_proxies = getattr(settings, "KEEL_API_THROTTLE_NUM_PROXIES", None)

    if num_proxies is not None:
        if num_proxies == 0 or xff is None:
            return remote_addr
        addrs = xff.split(",")
        return addrs[-min(num_proxies, len(addrs))].strip()  # type: ignore[no-any-return]

    return "".join(xff.split()) if xff else remote_addr


class RateThrottle:
    """Base class: subclasses set ``scope`` and implement ``_cache_key``.
    Instantiate per request and call ``check(request)`` — raises
    ``Throttled`` (429, ``Retry-After``) rather than returning a bool, so
    call sites don't need their own branch on failure."""

    cache = default_cache
    timer = staticmethod(time.time)
    cache_format = "throttle_%(scope)s_%(ident)s"
    scope: str = ""
    rate_setting: str = ""

    def __init__(self, rate: str | None = None) -> None:
        # An explicit rate bypasses settings entirely — the same trick
        # tests/test_rate_limiting.py's DRF-era fixture throttles use
        # (subclass with a low `rate`), since a runtime settings override
        # has nothing left to affect once a view has already read it.
        # Here there is no import-time read to race, but tests still want
        # a throttle whose rate doesn't depend on env-derived settings.
        self._explicit_rate = rate

    def check(self, request: HttpRequest) -> None:
        rate: str | None = (
            self._explicit_rate
            if self._explicit_rate is not None
            else getattr(settings, self.rate_setting, None)
        )
        parsed = _parse_rate(rate)
        if parsed is None:
            return
        num_requests, duration = parsed

        key = self._cache_key(request)
        if key is None:
            return

        history: list[float] = self.cache.get(key, [])
        now: float = self.timer()

        while history and history[-1] <= now - duration:
            history.pop()

        if len(history) >= num_requests:
            remaining_duration = duration - (now - history[-1]) if history else float(duration)
            available_requests = num_requests - len(history) + 1
            wait = (
                remaining_duration / float(available_requests)
                if available_requests > 0
                else float(duration)
            )
            raise Throttled(wait=wait)

        history.insert(0, now)
        self.cache.set(key, history, duration)

    def _cache_key(self, request: HttpRequest) -> str | None:
        raise NotImplementedError


class AnonRateThrottle(RateThrottle):
    scope = "anon"
    rate_setting = "KEEL_API_THROTTLE_ANON_RATE"

    def _cache_key(self, request: HttpRequest) -> str | None:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": _get_ident(request)}


class UserRateThrottle(RateThrottle):
    scope = "user"
    rate_setting = "KEEL_API_THROTTLE_USER_RATE"

    def _cache_key(self, request: HttpRequest) -> str | None:
        user = getattr(request, "user", None)
        ident = user.pk if user is not None and user.is_authenticated else _get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


def throttle(request: HttpRequest) -> None:
    """Run both the anon and user throttles — mirrors
    ``DEFAULT_THROTTLE_CLASSES = [UserRateThrottle, AnonRateThrottle]``,
    each of which is a no-op for the request shape the other one covers."""
    AnonRateThrottle().check(request)
    UserRateThrottle().check(request)


class ThrottleMiddleware:
    """Runs ``throttle()`` ahead of routing for every ``/api/v1/`` request,
    Ninja auth or not. Placed after ``AuthenticationMiddleware`` in
    ``MIDDLEWARE`` (``config/settings/base.py``) so ``request.user`` is
    already populated — ``UserRateThrottle`` keys on it.

    A ``Throttled`` raised here is caught and rendered through the same
    envelope ``keel.core.ninja_exceptions`` uses for one consistent 429
    body, since this runs outside Ninja's own exception-handler dispatch."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path.startswith("/api/v1/"):
            try:
                throttle(request)
            except Throttled as exc:
                from keel.core.ninja_exceptions import domain_error_response

                return domain_error_response(exc)
        return self.get_response(request)
