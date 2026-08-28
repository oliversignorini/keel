"""URLconf for the dedicated ASGI stream service (PRD §4 system
architecture). Deliberately minimal —
this process exists to hold open SSE connections, not to serve the
rest of the API; everything else stays on ``config.urls`` /
``config.wsgi``, behind gunicorn."""

from django.http import HttpRequest, JsonResponse
from django.urls import path

from keel.jobs.sse import job_stream


def healthz(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("healthz/", healthz, name="stream-healthz"),
    path(
        "api/v1/orgs/<slug:org_slug>/jobs/stream/",
        job_stream,
        name="jobs-stream",
    ),
]
