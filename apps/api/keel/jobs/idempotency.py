"""``Idempotency-Key`` middleware (PRD §5.5.3; docs/plans/phase-5.5.md
5.5.3) — applies only to POST views that opt in via
``idempotency_scoped = True`` (``keel.jobs.viewsets.JobViewSet``),
scoped by user + organisation + key so one user's replayed key can
never surface another user's cached response.

Real duplicate-row prevention lives in ``keel/jobs/services.py``
(``create_job`` looks up an existing ``Job`` by the same key, inside
the same transaction as the credit hold, before creating a row) — this
middleware's job is to make a replay cheap (skip the view and the
service call entirely) and to close the race between two
near-simultaneous replays of the same key, via the atomic
``cache.add()`` claim below.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse

IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24
_CLAIMED = "claimed"


def _cache_key(request: HttpRequest, view_kwargs: dict[str, Any], idempotency_key: str) -> str:
    user_id = getattr(request.user, "pk", None) or "anon"
    org_slug = view_kwargs.get("org_slug", "")
    return f"idempotency:{user_id}:{org_slug}:{idempotency_key}"


class IdempotencyKeyMiddleware:
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

    def process_view(
        self,
        request: HttpRequest,
        view_func: Any,
        view_args: tuple[Any, ...],
        view_kwargs: dict[str, Any],
    ) -> HttpResponse | None:
        if request.method != "POST":
            return None
        view_cls = getattr(view_func, "cls", None)
        if not getattr(view_cls, "idempotency_scoped", False):
            return None
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return None
        if not getattr(request.user, "is_authenticated", False):
            return None

        cache_key = _cache_key(request, view_kwargs, idempotency_key)
        cached = cache.get(cache_key)
        if isinstance(cached, dict) and "body" in cached:
            return JsonResponse(cached["body"], status=cached["status"])
        if cached == _CLAIMED:
            # A concurrent request with the same key is already in
            # flight. No second row is created either way; asking this
            # one to retry is simpler and just as correct as a spin-wait.
            return JsonResponse(
                {
                    "error": {
                        "code": "idempotency_key_in_progress",
                        "message": (
                            "A request with this Idempotency-Key is already being processed."
                        ),
                        "details": None,
                    }
                },
                status=409,
            )
        if cache.add(cache_key, _CLAIMED, timeout=IDEMPOTENCY_TTL_SECONDS):
            request.idempotency_cache_key = cache_key  # type: ignore[attr-defined]
        return None
