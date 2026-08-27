"""``Idempotency-Key`` handling (PRD §5.5.3; docs/plans/phase-5.5.md
5.5.3), scoped by user + a caller-supplied scope + key so one user's
replayed key can never surface another user's cached response, and one
endpoint's key can never collide with another endpoint's.

Originally lived in ``keel/jobs/idempotency.py`` — it was never actually
jobs-specific (api-patterns finding 10): a retried POST over a flaky
connection can duplicate a Stripe checkout session, an invitation email,
an upload row, or an organisation exactly the way it can duplicate a job.
This module is the generalised mechanism; ``@idempotent`` below is what a
view applies, in place of the one-off ``check_and_claim`` call
``keel.jobs.views.create_job`` used to make by hand.

Real duplicate-row prevention still lives in each service that has one
(e.g. ``keel/jobs/services.py::create_job`` looks up an existing ``Job``
by the same key, inside the same transaction as the credit hold, before
creating a row, and now backs that with a database
``UniqueConstraint`` — ddia#11) — this module's job is to make a replay
cheap (skip the view and the service call entirely) and to close the
race between two near-simultaneous replays of the same key, via the
atomic ``cache.add()`` claim below.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse

from keel.core.exceptions import Conflict

IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24
_CLAIMED = "claimed"


def _cache_key(request: HttpRequest, scope: str, idempotency_key: str) -> str:
    user_id = getattr(request.user, "pk", None) or "anon"
    return f"idempotency:{user_id}:{scope}:{idempotency_key}"


class IdempotencyKeyMiddleware:
    """Records the response ``check_and_claim`` claimed a cache key for.
    Framework-independent: keyed off ``request.idempotency_cache_key``, a
    plain attribute any view (DRF or Ninja) can set."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.idempotency_cache_key = None  # type: ignore[attr-defined]
        response = self.get_response(request)
        cache_key = getattr(request, "idempotency_cache_key", None)
        if cache_key and 200 <= response.status_code < 300:
            cache.set(
                cache_key,
                {"status": response.status_code, "body": json.loads(response.content or b"{}")},
                timeout=IDEMPOTENCY_TTL_SECONDS,
            )
        elif cache_key:
            # The attempt failed — free the key so a genuine retry isn't
            # locked out by its own failed predecessor.
            cache.delete(cache_key)
        return response


def check_and_claim(request: HttpRequest, scope: str) -> HttpResponse | None:
    """Called at the top of an idempotency-scoped view — directly, or via
    ``@idempotent`` below. ``scope`` disambiguates one endpoint's key
    space from another's (and, for an org-scoped endpoint, one
    organisation's from another's) — a bare user + key pair is not
    unique across the whole API. Returns a response to return
    immediately (a cached replay) or ``None`` to proceed — in which case
    ``request.idempotency_cache_key`` is set so ``IdempotencyKeyMiddleware``
    records the eventual response against it. Raises ``Conflict`` (409,
    through the standard error envelope — api-patterns finding 11) for a
    concurrent in-flight replay."""
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return None
    if not getattr(request.user, "is_authenticated", False):
        return None

    cache_key = _cache_key(request, scope, idempotency_key)
    cached = cache.get(cache_key)
    if isinstance(cached, dict) and "body" in cached:
        return JsonResponse(cached["body"], status=cached["status"])
    if cached == _CLAIMED:
        raise _in_progress_conflict()
    if cache.add(cache_key, _CLAIMED, timeout=IDEMPOTENCY_TTL_SECONDS):
        request.idempotency_cache_key = cache_key  # type: ignore[attr-defined]
        return None
    # cache.add lost the race (ddia#11): another request claimed this key
    # between our cache.get above and this cache.add — the exact
    # concurrent-replay case _CLAIMED above exists to catch. Falling
    # through to None here would let this request proceed and create a
    # second row; raise the same conflict instead.
    raise _in_progress_conflict()


def _in_progress_conflict() -> Conflict:
    # A concurrent request with the same key is already in flight. No
    # second row is created either way; asking this one to retry is
    # simpler and just as correct as a spin-wait. Raised, not
    # hand-returned, so it goes through keel.core.ninja_exceptions like
    # every other domain error (api-patterns finding 11) instead of a
    # second, untested copy of the envelope shape.
    return Conflict(
        code="idempotency_key_in_progress",
        message="A request with this Idempotency-Key is already being processed.",
    )


def idempotent(view_func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator form of ``check_and_claim`` for a Ninja route function
    (api-patterns finding 10): apply to any side-effectful POST with a
    real external effect worth deduplicating. Scopes the cache key by the
    decorated function's own identity plus ``org_slug`` (when the route
    has one) so two different endpoints — or the same endpoint called for
    two different organisations — never share a key space, and the
    caller-visible response (a fresh 201/202/200, or a 200 replay) is
    unchanged from calling the view directly.

    Must be the innermost decorator — apply the router method
    (``@router.post(...)``) around this, not the reverse, so Ninja's
    signature introspection (which follows ``functools.wraps``'s
    ``__wrapped__``) still sees the real view's parameters."""
    scope = f"{view_func.__module__}.{view_func.__qualname__}"

    @wraps(view_func)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        org_slug = kwargs.get("org_slug", "")
        replay = check_and_claim(request, f"{scope}:{org_slug}")
        if replay is not None:
            return replay
        return view_func(request, *args, **kwargs)

    return wrapper
