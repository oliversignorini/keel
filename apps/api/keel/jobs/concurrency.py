"""Per-organisation concurrency limits via a Redis semaphore (PRD §5.5.4;
docs/plans/phase-5.5.md 5.5.4).

The acceptance criterion is fairness, not throughput: one organisation
saturating its limit must not delay another organisation's job. A
semaphore that blocks the Celery worker process while waiting for a
slot would violate that directly — a blocked worker can't pick up any
other organisation's task either, shared-pool or not. So
``try_acquire`` never blocks: it returns ``False`` immediately when the
organisation is at its limit, and the caller (``jobs/runner.py``)
re-queues its own task a few seconds out and returns, freeing the
worker slot for someone else's job in the meantime.

The semaphore itself is a Redis sorted set of in-flight job ids scored
by acquisition time, with stale members pruned on every acquire
attempt — a worker that crashes while holding a slot self-heals after
``LEASE_SECONDS`` rather than leaking the slot forever. Acquire is a
single Lua script so the prune-count-add sequence is atomic against
concurrent acquire attempts from other workers.
"""

from __future__ import annotations

import time
from typing import Any

from django.conf import settings
from redis import Redis

_ACQUIRE_SCRIPT = """
local key = KEYS[1]
local member = ARGV[1]
local now = tonumber(ARGV[2])
local lease = tonumber(ARGV[3])
local limit = tonumber(ARGV[4])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - lease)
local count = redis.call('ZCARD', key)
if redis.call('ZSCORE', key, member) then
    redis.call('ZADD', key, now, member)
    return 1
end
if count < limit then
    redis.call('ZADD', key, now, member)
    return 1
end
return 0
"""

LEASE_SECONDS = 3600


def _redis_url() -> str:
    return str(getattr(settings, "JOBS_REDIS_URL", None) or settings.CELERY_BROKER_URL)


def default_limit() -> int:
    return int(getattr(settings, "JOBS_MAX_CONCURRENT_PER_ORG", 3))


class OrgConcurrencyLimiter:
    """One instance per process is fine — it holds no per-call state, only
    a Redis connection. ``client`` is injectable for tests."""

    def __init__(self, client: Redis | None = None, limit: int | None = None) -> None:
        self.client = client or Redis.from_url(_redis_url())
        self.limit = limit if limit is not None else default_limit()
        self._acquire = self.client.register_script(_ACQUIRE_SCRIPT)

    def _key(self, organization_id: Any) -> str:
        return f"jobs:concurrency:{organization_id}"

    def try_acquire(self, organization_id: Any, job_id: Any) -> bool:
        result = self._acquire(
            keys=[self._key(organization_id)],
            args=[str(job_id), time.time(), LEASE_SECONDS, self.limit],
        )
        return bool(result)

    def release(self, organization_id: Any, job_id: Any) -> None:
        self.client.zrem(self._key(organization_id), str(job_id))

    def current_count(self, organization_id: Any) -> int:
        key = self._key(organization_id)
        self.client.zremrangebyscore(key, "-inf", time.time() - LEASE_SECONDS)
        return int(self.client.zcard(key))
