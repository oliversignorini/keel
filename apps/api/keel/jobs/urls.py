"""URL wiring for jobs (PRD §7). Registered under the same
``organizations/<org_slug>/`` prefix as ``keel.organizations.urls``'s
nested router, and folded into that app's ``api_registry`` (see the
edit there) so the tenant-isolation meta-test (PRD §4 invariant 7)
walks ``JobViewSet`` too.

The stream endpoint is deliberately not here — it is served by the
dedicated ASGI service, never by this (sync) urlconf; see
``keel/jobs/sse.py`` and ``config/urls_stream.py``.
"""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from keel.jobs import viewsets

nested_router = SimpleRouter(trailing_slash=True)
nested_router.register("jobs", viewsets.JobViewSet, basename="job")

urlpatterns = [
    path("organizations/<slug:org_slug>/", include(nested_router.urls)),
]
