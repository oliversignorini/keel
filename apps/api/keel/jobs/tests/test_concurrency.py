"""Per-organisation concurrency limits via a Redis semaphore (PRD §5.5.4).

Runs against a real Redis (the dev stack's, same as every other
Redis-backed test in this suite) rather than a mock — the whole point
of this module is atomicity of the acquire under contention, which a
mock can't meaningfully exercise.
"""

import uuid

import pytest
from django.conf import settings
from redis import Redis

from keel.jobs.concurrency import OrgConcurrencyLimiter


def _limiter(limit: int) -> OrgConcurrencyLimiter:
    client = Redis.from_url(settings.JOBS_REDIS_URL)
    return OrgConcurrencyLimiter(client=client, limit=limit)


def _org_id() -> str:
    return f"test-org-{uuid.uuid4()}"


def test_acquire_succeeds_up_to_the_limit_then_is_refused() -> None:
    limiter = _limiter(limit=2)
    org = _org_id()
    assert limiter.try_acquire(org, "job-1") is True
    assert limiter.try_acquire(org, "job-2") is True
    assert limiter.try_acquire(org, "job-3") is False
    limiter.release(org, "job-1")
    limiter.release(org, "job-2")


def test_release_frees_a_slot_for_the_next_job() -> None:
    limiter = _limiter(limit=1)
    org = _org_id()
    assert limiter.try_acquire(org, "job-1") is True
    assert limiter.try_acquire(org, "job-2") is False
    limiter.release(org, "job-1")
    assert limiter.try_acquire(org, "job-2") is True
    limiter.release(org, "job-2")


def test_re_acquiring_a_held_slot_is_idempotent_and_does_not_consume_another() -> None:
    limiter = _limiter(limit=1)
    org = _org_id()
    assert limiter.try_acquire(org, "job-1") is True
    assert limiter.try_acquire(org, "job-1") is True
    limiter.release(org, "job-1")


def test_two_organizations_have_independent_limits() -> None:
    limiter = _limiter(limit=1)
    org_a, org_b = _org_id(), _org_id()
    assert limiter.try_acquire(org_a, "job-a") is True
    assert limiter.try_acquire(org_a, "job-a2") is False
    # Org B is unaffected by org A being saturated — the acceptance
    # criterion this whole module exists to satisfy.
    assert limiter.try_acquire(org_b, "job-b") is True
    limiter.release(org_a, "job-a")
    limiter.release(org_b, "job-b")


def test_current_count_reflects_held_slots() -> None:
    limiter = _limiter(limit=5)
    org = _org_id()
    assert limiter.current_count(org) == 0
    limiter.try_acquire(org, "job-1")
    limiter.try_acquire(org, "job-2")
    assert limiter.current_count(org) == 2
    limiter.release(org, "job-1")
    assert limiter.current_count(org) == 1
    limiter.release(org, "job-2")


@pytest.mark.django_db
def test_default_limit_reads_settings(settings) -> None:
    settings.JOBS_MAX_CONCURRENT_PER_ORG = 7
    limiter = OrgConcurrencyLimiter(client=Redis.from_url(settings.JOBS_REDIS_URL))
    assert limiter.limit == 7


def test_renew_refreshes_a_held_slot_without_consuming_another() -> None:
    """The step-boundary heartbeat (``run_job``) calls this —
    proves it succeeds for a slot already held even when the semaphore is
    fully saturated, and that it does not itself count as a new
    acquisition."""
    limiter = _limiter(limit=1)
    org = _org_id()
    assert limiter.try_acquire(org, "job-1") is True
    assert limiter.renew(org, "job-1") is True
    assert limiter.current_count(org) == 1
    limiter.release(org, "job-1")


def test_acquire_reads_time_from_redis_not_the_caller() -> None:
    """A worker with a skewed local clock must not decide expiry
    — this module must not import ``time`` at all, so there is nothing
    for a caller's clock to feed in; ``TIME`` is read inside the Lua
    script from Redis's own clock instead."""
    import keel.jobs.concurrency as concurrency_module

    assert not hasattr(concurrency_module, "time")
