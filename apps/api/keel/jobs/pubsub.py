"""Redis pub/sub publication of step transitions (PRD §5.5.5;
docs/plans/phase-5.5.md 5.5.5).

One channel per organisation rather than per job: ``<JobTray>`` shows
every job an organisation has in flight at once, and a single
subscription that carries every job's events is one connection per
browser tab instead of one per running job — relevant given HTTP/1.1's
six-connections-per-host cap the plan calls out as the third, smaller
footgun.

The publisher (this module, used from ``keel/jobs/runner.py``, a sync
Celery task) uses the sync ``redis`` client. The subscriber
(``keel/jobs/sse.py``, running on the dedicated ASGI service) uses
``redis.asyncio`` directly — no seam is needed between them since pub/sub
messages are just bytes on a channel name.
"""

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


def publish_event(organization_id: Any, event: dict[str, Any]) -> None:
    _get_client().publish(channel_for_organization(organization_id), json.dumps(event))


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
