"""General API rate limiting (PRD §3 NFR "Security"; docs/plans/phase-8.md
8.6): "Rate limits return 429 with Retry-After" in the standard error
envelope. allauth's own limiter covers /_allauth/*; this is the general
DRF-throttling path — the same ``UserRateThrottle``/``AnonRateThrottle``
classes and ``keel.core.exceptions.exception_handler`` production views
use, driven directly against a fixture view rather than a real settings
override.

Why a fixture view: ``APIView.throttle_classes`` reads
``api_settings.DEFAULT_THROTTLE_CLASSES`` once, when ``rest_framework.
views`` is first imported — already baked into every production view by
the time this test module runs, so a runtime ``settings.REST_FRAMEWORK``
override here has nothing left to affect (proven the hard way: the first
version of this test overrode settings and still saw 200 on the second
request). Subclassing the throttle with an explicit low ``rate`` sidesteps
that entirely and is also the more direct proof — the same shape
``keel.organizations.tests.test_end_to_end_denial``'s fixture viewsets
use to prove the permission-denial plumbing without a real router.
"""

import pytest
from django.core.cache import cache
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from keel.accounts.models import User
from keel.core.exceptions import exception_handler

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _isolated_throttle_state():
    """Throttle counters live in the shared Redis cache, keyed by client
    IP / user id — the same key format the real ``AnonRateThrottle`` /
    ``UserRateThrottle`` use, since the fixture classes below only
    override ``rate``, not ``scope``. Cleared so this file's "first
    request succeeds" assumption can't be tripped by unrelated activity
    (another test run, a developer's own dev server) sharing the same
    cache."""
    cache.clear()
    yield
    cache.clear()


class _StrictAnonThrottle(AnonRateThrottle):
    rate = "1/min"


class _StrictUserThrottle(UserRateThrottle):
    rate = "1/min"


class _AnonThrottledView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (_StrictAnonThrottle,)

    def get_exception_handler(self):
        return exception_handler

    def get(self, request):
        return Response({"ok": True})


class _UserThrottledView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_classes = (_StrictUserThrottle,)

    def get_exception_handler(self):
        return exception_handler

    def get(self, request):
        return Response({"ok": True})


def test_exceeding_the_anon_rate_returns_429_with_retry_after() -> None:
    view = _AnonThrottledView.as_view()
    factory = APIRequestFactory()

    first = view(factory.get("/fixture/anon-throttled/"))
    second = view(factory.get("/fixture/anon-throttled/"))

    assert first.status_code == 200
    assert second.status_code == 429
    assert "Retry-After" in second
    assert int(second["Retry-After"]) > 0
    assert second.data["error"]["code"] == "throttled"


def test_exceeding_the_user_rate_returns_429_with_retry_after() -> None:
    user = User.objects.create_user(email="throttled@example.com", password="s3cret-pass")
    view = _UserThrottledView.as_view()
    factory = APIRequestFactory()

    def _request():
        request = factory.get("/fixture/user-throttled/")
        request.user = user
        return view(request)

    first = _request()
    second = _request()

    assert first.status_code == 200
    assert second.status_code == 429
    assert "Retry-After" in second
    assert second.data["error"]["code"] == "throttled"


def test_two_different_users_do_not_share_a_throttle_bucket() -> None:
    """Proves the counter is keyed per user, not global — otherwise one
    busy account would rate-limit every other tenant."""
    user_a = User.objects.create_user(email="a@example.com", password="s3cret-pass")
    user_b = User.objects.create_user(email="b@example.com", password="s3cret-pass")
    view = _UserThrottledView.as_view()
    factory = APIRequestFactory()

    def _request(user):
        request = factory.get("/fixture/user-throttled/")
        request.user = user
        return view(request)

    assert _request(user_a).status_code == 200
    assert _request(user_b).status_code == 200
