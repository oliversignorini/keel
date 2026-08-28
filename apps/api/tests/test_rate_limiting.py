"""General API rate limiting (PRD §3 NFR "Security"): "Rate limits return
429 with Retry-After" in the standard error envelope. allauth's own
limiter covers /_allauth/*; this is the general path every
``/api/v1/`` request runs through — ``keel.core.throttle``'s
``UserRateThrottle`` / ``AnonRateThrottle``, applied by
``ThrottleMiddleware`` ahead of routing.

Why explicit ``rate=`` rather than a settings override: config/settings/
test.py sets ``KEEL_API_THROTTLE_USER_RATE`` / ``_ANON_RATE`` to ``None``
so hundreds of unrelated tests can't trip each other's counters in the
shared Redis cache. Constructing a throttle with an explicit low rate
bypasses settings entirely (``RateThrottle.__init__``) and is also the
more direct proof of the mechanism itself.
"""

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from keel.accounts.models import User
from keel.core.exceptions import Throttled
from keel.core.throttle import AnonRateThrottle, UserRateThrottle

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _isolated_throttle_state():
    """Throttle counters live in the shared Redis cache, keyed by client
    IP / user id — the same key format the real throttles use, since the
    instances below only override ``rate``, not ``scope``. Cleared so this
    file's "first request succeeds" assumption can't be tripped by
    unrelated activity (another test run, a developer's own dev server)
    sharing the same cache."""
    cache.clear()
    yield
    cache.clear()


def _anon_request():
    return RequestFactory().get("/api/v1/fixture/")


def _user_request(user):
    request = RequestFactory().get("/api/v1/fixture/")
    request.user = user
    return request


def test_exceeding_the_anon_rate_returns_429_with_retry_after() -> None:
    throttle = AnonRateThrottle(rate="1/min")

    throttle.check(_anon_request())

    with pytest.raises(Throttled) as excinfo:
        throttle.check(_anon_request())

    exc = excinfo.value
    assert exc.status_code == 429
    assert exc.code == "throttled"
    # `wait` is what keel.core.error_handlers turns into Retry-After.
    assert exc.wait is not None
    assert int(exc.wait) > 0


def test_exceeding_the_user_rate_returns_429_with_retry_after() -> None:
    user = User.objects.create_user(email="throttled@example.com", password="s3cret-pass")
    throttle = UserRateThrottle(rate="1/min")

    throttle.check(_user_request(user))

    with pytest.raises(Throttled) as excinfo:
        throttle.check(_user_request(user))

    exc = excinfo.value
    assert exc.status_code == 429
    assert exc.code == "throttled"
    assert exc.wait is not None


def test_two_different_users_do_not_share_a_throttle_bucket() -> None:
    """Proves the counter is keyed per user, not global — otherwise one
    busy account would rate-limit every other tenant."""
    user_a = User.objects.create_user(email="a@example.com", password="s3cret-pass")
    user_b = User.objects.create_user(email="b@example.com", password="s3cret-pass")
    throttle = UserRateThrottle(rate="1/min")

    throttle.check(_user_request(user_a))
    throttle.check(_user_request(user_b))  # must not raise


def test_check_returns_rate_limit_headers_on_success() -> None:
    """api-patterns finding 7: a successful request under a throttled
    scope still learns the policy, not only a request that gets 429'd."""
    throttle = UserRateThrottle(rate="5/min")
    user = User.objects.create_user(email="paced@example.com", password="s3cret-pass")

    headers = throttle.check(_user_request(user))

    assert headers is not None
    assert headers["X-RateLimit-Limit"] == "5"
    assert headers["X-RateLimit-Remaining"] == "4"
    assert int(headers["X-RateLimit-Reset"]) > 0


def test_throttled_exception_carries_rate_limit_headers_with_zero_remaining() -> None:
    throttle = AnonRateThrottle(rate="1/min")
    throttle.check(_anon_request())

    with pytest.raises(Throttled) as excinfo:
        throttle.check(_anon_request())

    headers = excinfo.value.response_headers
    assert headers["X-RateLimit-Limit"] == "1"
    assert headers["X-RateLimit-Remaining"] == "0"
    assert "Retry-After" in headers


def test_middleware_sets_rate_limit_headers_on_a_successful_response(settings, client) -> None:
    """End-to-end through ThrottleMiddleware (config/settings/base.py),
    not the throttle classes directly — proves the headers actually ride
    on the response a client receives, on a real public route."""
    settings.KEEL_API_THROTTLE_ANON_RATE = "5/min"
    settings.KEEL_API_THROTTLE_USER_RATE = "300/min"

    response = client.get("/api/v1/plans/")

    assert response.status_code == 200
    assert response["X-RateLimit-Limit"] == "5"
    assert response["X-RateLimit-Remaining"] == "4"
    assert response["X-RateLimit-Reset"]


def test_middleware_sets_rate_limit_headers_on_a_429_response(settings, client) -> None:
    settings.KEEL_API_THROTTLE_ANON_RATE = "1/min"
    settings.KEEL_API_THROTTLE_USER_RATE = "300/min"

    client.get("/api/v1/plans/")
    response = client.get("/api/v1/plans/")

    assert response.status_code == 429
    assert response["X-RateLimit-Limit"] == "1"
    assert response["X-RateLimit-Remaining"] == "0"
    assert response["Retry-After"]


def test_disabled_throttle_returns_no_headers() -> None:
    """rate=None (config/settings/test.py's default for the whole suite)
    is a real, supported "off" state, not just a test-isolation trick —
    it must not fabricate headers for a limit that doesn't apply."""
    throttle = UserRateThrottle(rate=None)

    assert (
        throttle.check(
            _user_request(
                User.objects.create_user(email="unlimited@example.com", password="s3cret-pass")
            )
        )
        is None
    )
