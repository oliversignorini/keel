"""``keel.core.idempotency`` (api-patterns finding 10/11) — generalised
out of ``keel/jobs`` because a retried POST can duplicate a checkout
session, an invitation email, an upload row or an organisation exactly
the way it can duplicate a job.

Every test below mints a fresh, random ``Idempotency-Key`` per case
rather than a fixed literal — this project's real Redis cache persists
across test runs (config/settings/test.py's rationale for
``ACCOUNT_RATE_LIMITS``/``KEEL_API_THROTTLE_*``, the same underlying
store), so a literal key claimed by one run is still "claimed" the next
time the suite runs and the test fails against leftover state rather
than what it wrote."""

import uuid
from unittest.mock import MagicMock

import pytest
from django.core.cache import cache
from django.http import JsonResponse
from django.test import RequestFactory

from keel.core.exceptions import Conflict
from keel.core.idempotency import check_and_claim, idempotent


def _key() -> str:
    return f"test-{uuid.uuid4()}"


def _request(headers: dict | None = None, authenticated: bool = True):
    meta = {
        f"HTTP_{name.upper().replace('-', '_')}": value for name, value in (headers or {}).items()
    }
    request = RequestFactory().post("/whatever/", **meta)
    request.user = MagicMock(pk=uuid.uuid4(), is_authenticated=authenticated)
    return request


def test_no_header_is_a_no_op() -> None:
    assert check_and_claim(_request(), "scope") is None


def test_anonymous_caller_is_a_no_op() -> None:
    request = _request(headers={"Idempotency-Key": _key()}, authenticated=False)
    assert check_and_claim(request, "scope") is None


def test_first_claim_proceeds_and_sets_the_cache_key() -> None:
    request = _request(headers={"Idempotency-Key": _key()})
    assert check_and_claim(request, "scope-a") is None
    assert request.idempotency_cache_key is not None


def test_a_concurrent_claim_raises_conflict_not_a_hand_built_response() -> None:
    """api-patterns finding 11: this must go through
    keel.core.error_handlers like every other domain error, not a
    second, untested copy of the envelope."""
    key = _key()
    request = _request(headers={"Idempotency-Key": key})
    check_and_claim(request, "scope-b")  # claims it

    second_request = _request(headers={"Idempotency-Key": key})
    second_request.user = request.user  # same caller — the actual race
    with pytest.raises(Conflict) as exc_info:
        check_and_claim(second_request, "scope-b")
    assert exc_info.value.code == "idempotency_key_in_progress"
    assert exc_info.value.status_code == 409


def test_a_cached_response_is_replayed_without_calling_the_view() -> None:
    request = _request(headers={"Idempotency-Key": _key()})
    cache_key = f"idempotency:{request.user.pk}:scope-c:{request.headers['Idempotency-Key']}"
    cache.set(cache_key, {"status": 201, "body": {"id": "abc"}}, timeout=60)

    response = check_and_claim(request, "scope-c")

    assert isinstance(response, JsonResponse)
    assert response.status_code == 201


def test_two_different_scopes_never_collide() -> None:
    """The whole point of moving this out of keel/jobs — two endpoints
    replaying the same header value by coincidence must not share a
    cache key."""
    key = _key()
    user = MagicMock(pk=uuid.uuid4(), is_authenticated=True)

    request_a = _request(headers={"Idempotency-Key": key})
    request_a.user = user
    assert check_and_claim(request_a, "endpoint-a") is None

    request_b = _request(headers={"Idempotency-Key": key})
    request_b.user = user
    assert check_and_claim(request_b, "endpoint-b") is None  # not a conflict


def test_idempotent_decorator_scopes_by_view_identity_and_org_slug() -> None:
    calls = []

    @idempotent
    def a_view(request, org_slug=None):
        calls.append(org_slug)
        return {"ok": True}

    key = _key()
    user = MagicMock(pk=uuid.uuid4(), is_authenticated=True)

    def _req():
        request = _request(headers={"Idempotency-Key": key})
        request.user = user
        return request

    a_view(_req(), org_slug="org-1")

    with pytest.raises(Conflict):
        a_view(_req(), org_slug="org-1")

    # A different org_slug is a different scope entirely — proceeds.
    a_view(_req(), org_slug="org-2")

    assert calls == ["org-1", "org-2"]
