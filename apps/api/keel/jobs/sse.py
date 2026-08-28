"""The SSE endpoint (PRD §5.5.5) — served only by the dedicated ASGI
service (``config/asgi_stream.py`` / ``config/urls_stream.py``), never
by the sync gunicorn process. This is footgun 1: under a sync worker
model every open browser tab occupies a worker for the connection's
entire life, and the pool exhausts far below what request/response
load testing would suggest.

Two things here exist specifically to defeat footgun 2 (a reverse
proxy buffering ``text/event-stream`` by default, which turns "streams
live" into "shows nothing for minutes, then everything at once"):

- the leading ``: connected\n\n`` comment, flushed before the first
  real event so the browser — and any proxy in front of it — sees
  bytes immediately rather than waiting for the first job event to
  exist
- the ``X-Accel-Buffering: no`` header, the standard signal to turn
  proxy buffering off for this response specifically, without touching
  the API's ordinary traffic

Streams events for every job in the organisation, not just one — see
``keel/jobs/pubsub.py``'s docstring for why the channel is per-org
rather than per-job.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from asgiref.sync import sync_to_async
from django.http import (
    HttpRequest,
    HttpResponseBase,
    HttpResponseForbidden,
    HttpResponseNotFound,
    StreamingHttpResponse,
)
from redis import asyncio as aioredis

from keel.jobs.pubsub import channel_for_organization, redis_url
from keel.organizations.permissions import Perm, has_perm
from keel.organizations.resolvers import resolve_organization

HEARTBEAT_SECONDS = 15.0


async def _event_stream(request: HttpRequest, organization_id: str) -> AsyncIterator[bytes]:
    client = aioredis.from_url(redis_url())
    pubsub = client.pubsub()
    channel = channel_for_organization(organization_id)
    await pubsub.subscribe(channel)
    try:
        # Flushed before touching Redis again: the first byte this
        # endpoint exists to protect must reach the client with zero
        # Redis-related delay, not after the priming read below.
        yield b": connected\n\n"

        # A message published in the gap between subscribe() completing
        # and this coroutine's first real get_message() call is
        # otherwise missed entirely — not delayed, dropped. redis-py's
        # async pubsub connection needs one get_message() call to
        # actually run (a timeout=0 no-op call does not count — verified
        # empirically down to the millisecond) before it reliably
        # surfaces data on later calls; a short priming read closes that
        # gap, off the hot "first byte" path. Its result is real data,
        # not a throwaway — a step transition published in that exact
        # window must still reach the client, not be swallowed by the
        # read that was only meant to warm up the connection.
        primed = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
        pending = [primed] if primed is not None else []

        # Django's ASGI handler has no Starlette-style
        # ``request.is_disconnected()`` — there is no such method on
        # ``HttpRequest``. Disconnect is instead detected the way the
        # rest of Django's ASGI stack does it: uvicorn cancels this
        # coroutine (raising into whichever ``await`` is suspended)
        # when the client goes away, which unwinds straight into the
        # ``finally`` block below to clean up the subscription.
        while True:
            if pending:
                message = pending.pop()
            else:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=HEARTBEAT_SECONDS
                )
            if message is None:
                yield b": heartbeat\n\n"
                continue
            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode()
            yield f"event: job\ndata: {data}\n\n".encode()
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await client.aclose()


async def job_stream(request: HttpRequest, org_slug: str) -> HttpResponseBase:
    organization = await sync_to_async(resolve_organization)(request, org_slug)
    if organization is None:
        return HttpResponseNotFound()

    user = await request.auser()
    decision = await sync_to_async(has_perm)(user, organization, Perm.JOBS_VIEW)
    if not decision.allowed:
        return HttpResponseForbidden()

    response = StreamingHttpResponse(
        _event_stream(request, str(organization.id)),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    response["Connection"] = "keep-alive"
    return response
