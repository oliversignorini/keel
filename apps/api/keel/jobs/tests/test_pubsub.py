"""Sequence numbers on published events — Redis pub/sub is
at-most-once with no buffer, so ``seq`` is what lets a reconnecting
client detect a gap and refetch rather than trust a stream it knows
skipped something. See ``keel/jobs/pubsub.py``'s module docstring."""

import json
import uuid

import pytest
from django.conf import settings
from redis import Redis

from keel.jobs.pubsub import channel_for_organization, next_seq, publish_event


@pytest.fixture
def redis_client() -> Redis:
    return Redis.from_url(settings.JOBS_REDIS_URL)


def test_seq_is_monotonically_increasing_per_organization() -> None:
    org = str(uuid.uuid4())
    first = next_seq(org)
    second = next_seq(org)
    third = next_seq(org)
    assert (first, second, third) == (first, first + 1, first + 2)


def test_seq_is_independent_per_organization() -> None:
    org_a, org_b = str(uuid.uuid4()), str(uuid.uuid4())
    next_seq(org_a)
    next_seq(org_a)
    assert next_seq(org_b) == 1


def test_published_events_carry_a_seq(redis_client: Redis) -> None:
    org = str(uuid.uuid4())
    pubsub = redis_client.pubsub()
    pubsub.subscribe(channel_for_organization(org))
    pubsub.get_message(timeout=1)  # the subscribe confirmation

    publish_event(org, {"type": "job", "job_id": "abc"})

    message = pubsub.get_message(timeout=1)
    payload = json.loads(message["data"])
    assert isinstance(payload["seq"], int)
    assert payload["job_id"] == "abc"
    pubsub.close()
