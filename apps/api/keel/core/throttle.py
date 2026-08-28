"""Rate limiting for Ninja routes (PRD §3 NFR "Security": "Rate limiting
... on the API generally"; docs/plans/phase-8.md 8.6).

A cache-backed sliding window over Django's cache (Redis in production),
configured by ``KEEL_API_THROTTLE_USER_RATE`` / ``_ANON_RATE``, answering
429 + ``Retry-After`` on the limit. Every throttled-scope response (429
or not) also carries ``X-RateLimit-Limit`` / ``-Remaining`` / ``-Reset``,
so a client can pace itself before being rejected rather than learning
the policy only on failure (api-patterns finding 7).

Applied as a layer over every ``/api/v1/`` request (``ThrottleMiddleware``
below), not tucked inside the deny-by-default auth callables
(``keel.core.auth``) — a request that arrived is what gets rate limited,
regardless of whether the route it hit turns out to require a session.
Auth-gated routes and the project's public routers
(``keel.core.authz.public_router`` — ``GET /plans/``, the Stripe webhook)
are covered identically because neither ever calls
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
        # An explicit rate bypasses settings entirely — tests/test_rate_
        # limiting.py's fixture throttles use this (subclass with a low
        # `rate`), since a runtime settings override has nothing left to
        # affect once a view has already read it. Here there is no
        # import-time read to race, but tests still want a throttle whose
        # rate doesn't depend on env-derived settings.
        self._explicit_rate = rate

    def check(self, request: HttpRequest) -> dict[str, str] | None:
        """Returns the ``X-RateLimit-*`` headers reflecting this
        throttle's state after the check (api-patterns finding 7), or
        ``None`` when this throttle doesn't apply to the request at all
        (rate disabled, or ``_cache_key`` opted the request out — e.g.
        ``AnonRateThrottle`` on an authenticated request)."""
        rate: str | None = (
            self._explicit_rate
            if self._explicit_rate is not None
            else getattr(settings, self.rate_setting, None)
        )
        parsed = _parse_rate(rate)
        if parsed is None:
            return None
        num_requests, duration = parsed

        key = self._cache_key(request)
        if key is None:
            return None

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
            raise Throttled(
                wait=wait,
                headers=self._headers(num_requests, remaining=0, reset_at=now + remaining_duration),
            )

        history.insert(0, now)
        self.cache.set(key, history, duration)
        # history[-1] is the oldest surviving entry (insert(0, ...) keeps
        # newest-first) — the moment it ages out of the window is the
        # moment a slot frees up, which is the honest "Reset" value for a
        # sliding window rather than a fixed one.
        reset_at = history[-1] + duration
        return self._headers(num_requests, remaining=num_requests - len(history), reset_at=reset_at)

    @staticmethod
    def _headers(limit: int, *, remaining: int, reset_at: float) -> dict[str, str]:
        return {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(max(remaining, 0)),
            "X-RateLimit-Reset": str(int(reset_at)),
        }

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


def throttle(request: HttpRequest) -> dict[str, str]:
    """Run both the anon and user throttles — mirrors
    ``DEFAULT_THROTTLE_CLASSES = [UserRateThrottle, AnonRateThrottle]``,
    each of which is a no-op for the request shape the other one covers.

    Returns the ``X-RateLimit-*`` headers for whichever throttle is the
    binding constraint on this request: ``AnonRateThrottle``'s, when it
    applies (an anonymous caller is bound by the anon rate, which
    ``UserRateThrottle`` — keyed by IP for the same caller — also checks
    but at a looser rate), otherwise ``UserRateThrottle``'s. Raises
    ``Throttled`` on the first throttle that is over-limit, carrying that
    throttle's own headers (api-patterns finding 7)."""
    anon_headers = AnonRateThrottle().check(request)
    user_headers = UserRateThrottle().check(request)
    return anon_headers or user_headers or {}


class ThrottleMiddleware:
    """Runs ``throttle()`` ahead of routing for every ``/api/v1/`` request,
    Ninja auth or not. Placed after ``AuthenticationMiddleware`` in
    ``MIDDLEWARE`` (``config/settings/base.py``) so ``request.user`` is
    already populated — ``UserRateThrottle`` keys on it.

    A ``Throttled`` raised here is caught and rendered through the same
    envelope ``keel.core.error_handlers`` uses for one consistent 429
    body, since this runs outside Ninja's own exception-handler dispatch.
    The ``X-RateLimit-*`` headers ride on every throttled-scope response,
    not only the 429 — a client that never fails still learns how close
    it is to the limit (api-patterns finding 7: "the client can pace
    itself before being rejected")."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path.startswith("/api/v1/"):
            try:
                headers = throttle(request)
            except Throttled as exc:
                from keel.core.error_handlers import domain_error_response

                return domain_error_response(exc)
            response = self.get_response(request)
            for header, value in headers.items():
                response[header] = value
            return response
        return self.get_response(request)
