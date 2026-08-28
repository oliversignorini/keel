"""The SSE endpoint (PRD §5.5.5) — served only by ``config.urls_stream``,
exercised directly here against ``job_stream`` rather than through the
sync ``config.urls`` test client, matching how it is actually deployed
(a separate ASGI service; see ``config/asgi_stream.py``).

The acceptance criterion this file exists to prove: **first event
reaches the client in under one second** — the only assertion that
catches a reverse proxy silently buffering ``text/event-stream``.
``job_stream`` writes a
leading ``: connected`` comment before ever touching Redis, specifically
so there is a first byte to measure this against even before any job
event exists.
"""

import time
from collections.abc import AsyncGenerator
from typing import cast

import pytest
from asgiref.sync import sync_to_async
from django.http import StreamingHttpResponse
from django.test import RequestFactory

from keel.billing.tests.factories import make_organization, make_user
from keel.jobs.pubsub import channel_for_organization, publish_event
from keel.jobs.sse import job_stream
from keel.organizations.models import Membership, Role
from keel.organizations.roles import PRESET_OWNER, seed_preset_roles

# transaction=True: ``sync_to_async`` fixture calls in these tests run
# on worker threads with their own DB connection, separate from the
# main thread's — a plain (non-transactional) django_db wraps only the
# main thread's connection in a rollback-only transaction, and a
# worker-thread connection left mid-transaction when the test ends
# poisons the *next* test to reuse that connection from the pool
# (surfaced as an unrelated later test failing with an aborted-
# transaction cursor error). transaction=True gives each test real
# commits plus table-truncation cleanup, which is safe across threads.
pytestmark = pytest.mark.django_db(transaction=True)


async def _authed_member(organization):
    user = await sync_to_async(make_user)()
    role = (await sync_to_async(seed_preset_roles)())[PRESET_OWNER]
    await sync_to_async(Membership.objects.create)(
        organization=organization, user=user, role=role, status=Membership.STATUS_ACTIVE
    )
    return user


def _request_for(org_slug, user):
    """``RequestFactory`` builds a bare request with no middleware
    applied. ``auser`` is normally attached by
    ``AuthenticationMiddleware`` (it is not a base ``HttpRequest``
    method) — the production ASGI service runs the same
    ``settings.MIDDLEWARE`` as everything else, so this stub only
    stands in for what that middleware would already have done."""
    request = RequestFactory().get(f"/api/v1/orgs/{org_slug}/jobs/stream/")
    request.user = user

    async def auser():
        return user

    request.auser = auser
    return request


@pytest.mark.asyncio
async def test_first_event_reaches_the_client_in_under_one_second() -> None:
    organization = await sync_to_async(make_organization)()
    user = await _authed_member(organization)

    request = _request_for(organization.slug, user)

    started = time.perf_counter()
    response = await job_stream(request, organization.slug)
    assert response.status_code == 200
    assert response["Content-Type"] == "text/event-stream"
    assert response["X-Accel-Buffering"] == "no"

    response = cast(StreamingHttpResponse, response)
    stream = cast(AsyncGenerator[bytes, None], response.streaming_content)
    first_chunk = await stream.__anext__()
    elapsed = time.perf_counter() - started

    assert first_chunk == b": connected\n\n"
    assert elapsed < 1.0, f"first byte took {elapsed:.3f}s"
    await stream.aclose()


@pytest.mark.asyncio
async def test_a_published_job_event_is_delivered_on_the_stream() -> None:
    organization = await sync_to_async(make_organization)()
    user = await _authed_member(organization)

    request = _request_for(organization.slug, user)

    response = await job_stream(request, organization.slug)
    response = cast(StreamingHttpResponse, response)
    stream = cast(AsyncGenerator[bytes, None], response.streaming_content)

    await stream.__anext__()  # ": connected" — subscribe() has completed by now

    # Published only after the subscription is confirmed live, and
    # awaited to completion before the generator is resumed to read it
    # — no race with the heartbeat branch's timeout.
    await sync_to_async(publish_event)(
        str(organization.id), {"type": "job", "job_id": "abc", "status": "running"}
    )
    chunk = await stream.__anext__()

    assert chunk.startswith(b"event: job\ndata: ")
    assert b'"job_id": "abc"' in chunk
    await stream.aclose()


@pytest.mark.asyncio
async def test_a_non_member_gets_404_not_403() -> None:
    """Deliberately the same outcome as an unresolvable slug (PRD §4
    invariant 7) — a 403 here would confirm the organisation exists to
    someone outside it."""
    organization = await sync_to_async(make_organization)()
    outsider = await sync_to_async(make_user)()

    request = _request_for(organization.slug, outsider)

    response = await job_stream(request, organization.slug)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_member_without_jobs_view_is_forbidden() -> None:
    organization = await sync_to_async(make_organization)()
    member = await sync_to_async(make_user)()
    role = await sync_to_async(Role.objects.create)(
        organization=organization, name="Powerless", permissions=[]
    )
    await sync_to_async(Membership.objects.create)(
        organization=organization, user=member, role=role, status=Membership.STATUS_ACTIVE
    )

    request = _request_for(organization.slug, member)

    response = await job_stream(request, organization.slug)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_an_unknown_org_slug_404s() -> None:
    user = await sync_to_async(make_user)()
    request = _request_for("does-not-exist", user)

    response = await job_stream(request, "does-not-exist")
    assert response.status_code == 404


def test_channel_naming_is_stable_per_organization() -> None:
    assert channel_for_organization("abc") == "jobs:stream:abc"
