"""``Idempotency-Key`` handling (PRD §5.5.3; docs/plans/phase-5.5.md
5.5.3), scoped by user + organisation + key so one user's replayed key
can never surface another user's cached response.

Real duplicate-row prevention lives in ``keel/jobs/services.py``
(``create_job`` looks up an existing ``Job`` by the same key, inside
the same transaction as the credit hold, before creating a row) — this
module's job is to make a replay cheap (skip the view and the service
call entirely) and to close the race between two near-simultaneous
replays of the same key, via the atomic ``cache.add()`` claim below.

Before phase-10.md 10.C this was a DRF-view-attribute-driven Django
middleware (``idempotency_scoped = True`` on the viewset, detected via
``view_func.cls`` in ``process_view`` — a hook Ninja's routing has no
equivalent of: its per-path view functions aren't built through
Django's ``View.as_view()``, so they carry no ``.cls``). ``check_and_claim``
below is the same mechanism as an explicit call a Ninja view makes at
the top of its own body instead of an implicit, class-attribute-driven
one — see ``keel/jobs/views.py``'s ``create_job``. The response-recording
half (``IdempotencyKeyMiddleware.__call__``) needed no change: it was
already framework-independent, keyed off a plain request attribute.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse

IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24
_CLAIMED = "claimed"


def _cache_key(request: HttpRequest, org_slug: str, idempotency_key: str) -> str:
    user_id = getattr(request.user, "pk", None) or "anon"
    return f"idempotency:{user_id}:{org_slug}:{idempotency_key}"


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


def check_and_claim(request: HttpRequest, org_slug: str) -> HttpResponse | None:
    """Called explicitly at the top of an idempotency-scoped Ninja POST
    view. Returns a response to return immediately (a cached replay, or
    409 for a concurrent in-flight replay) or ``None`` to proceed — in
    which case ``request.idempotency_cache_key`` is set so
    ``IdempotencyKeyMiddleware`` records the eventual response against it."""
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return None
    if not getattr(request.user, "is_authenticated", False):
        return None

    cache_key = _cache_key(request, org_slug, idempotency_key)
    cached = cache.get(cache_key)
    if isinstance(cached, dict) and "body" in cached:
        return JsonResponse(cached["body"], status=cached["status"])
    if cached == _CLAIMED:
        return _in_progress_response()
    if cache.add(cache_key, _CLAIMED, timeout=IDEMPOTENCY_TTL_SECONDS):
        request.idempotency_cache_key = cache_key  # type: ignore[attr-defined]
        return None
    # cache.add lost the race (ddia#11): another request claimed this key
    # between our cache.get above and this cache.add — the exact
    # concurrent-replay case _CLAIMED above exists to catch. Falling
    # through to None here would let this request proceed and create a
    # second row; return the same in-progress response instead.
    return _in_progress_response()


def _in_progress_response() -> JsonResponse:
    # A concurrent request with the same key is already in flight. No
    # second row is created either way; asking this one to retry is
    # simpler and just as correct as a spin-wait.
    return JsonResponse(
        {
            "error": {
                "code": "idempotency_key_in_progress",
                "message": "A request with this Idempotency-Key is already being processed.",
                "details": None,
            }
        },
        status=409,
    )
