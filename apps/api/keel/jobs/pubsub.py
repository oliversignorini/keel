"""Redis pub/sub publication of step transitions (PRD §5.5.5).

One channel per organisation rather than per job: ``<JobTray>`` shows
every job an organisation has in flight at once, and a single
subscription that carries every job's events is one connection per
browser tab instead of one per running job — relevant given HTTP/1.1's
six-connections-per-host cap.

The publisher (this module, used from ``keel/jobs/runner.py``, a sync
Celery task) uses the sync ``redis`` client. The subscriber
(``keel/jobs/sse.py``, running on the dedicated ASGI service) uses
``redis.asyncio`` directly — no seam is needed between them since pub/sub
messages are just bytes on a channel name.

Every event carries a ``seq``: a per-organisation counter (``INCR``,
atomic) stamped on the way out. Redis pub/sub is at-most-once
with no buffer — a client that is disconnected when an event publishes
never receives it, and a bare event stream gives the client no way to
even notice a gap. ``seq`` doesn't fix that on its own (there is nothing
to replay from — this is not a Redis Stream), but it turns "silently
missed an event" into "detected a gap": a reconnecting client compares
the ``seq`` on the first event it receives against the last one it saw
before disconnecting and, on any gap, refetches ``GET
/orgs/<org_slug>/jobs/`` (already the source of truth for job state) to
resynchronise rather than trusting a stream it knows skipped something.
This is the cheaper of the two available fixes — a move to
Redis Streams (``XADD``/``XRANGE`` with ``Last-Event-ID`` replay) buys
true resumability, at the cost of a second Redis data structure and a
retention policy for it. The tray only ever needs "am I looking at the
current state", which a refetch answers exactly as well as a replayed
event log would; the seq number is what lets the client know *when* to
ask."""

from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from redis import Redis


def redis_url() -> str:
    return str(getattr(settings, "JOBS_REDIS_URL", None) or settings.CELERY_BROKER_URL)


def channel_for_organization(organization_id: Any) -> str:
    return f"jobs:stream:{organization_id}"


_client: Redis | None = None


def _get_client() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(redis_url())
    return _client


def _seq_key(organization_id: Any) -> str:
    return f"jobs:stream:seq:{organization_id}"


def next_seq(organization_id: Any) -> int:
    return int(_get_client().incr(_seq_key(organization_id)))


def publish_event(organization_id: Any, event: dict[str, Any]) -> None:
    stamped = {**event, "seq": next_seq(organization_id)}
    _get_client().publish(channel_for_organization(organization_id), json.dumps(stamped))


def job_event(job: Any) -> dict[str, Any]:
    return {
        "type": "job",
        "job_id": str(job.id),
        "status": job.status,
        "job_type": job.type,
        "result_ref": job.result_ref,
        "error": job.error,
    }


def step_event(job: Any, step: Any) -> dict[str, Any]:
    return {
        "type": "step",
        "job_id": str(job.id),
        "step_id": str(step.id),
        "name": step.name,
        "ordinal": step.ordinal,
        "status": step.status,
        "output_ref": step.output_ref,
        "error": step.error,
    }


def publish_job_event(job: Any) -> None:
    publish_event(job.organization_id, job_event(job))


def publish_step_event(job: Any, step: Any) -> None:
    publish_event(job.organization_id, step_event(job, step))
