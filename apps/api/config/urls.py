from django.conf import settings
from django.contrib import admin
from django.db import connections
from django.http import HttpRequest, JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView
from redis import Redis
from redis.exceptions import RedisError


def healthz(request: HttpRequest) -> JsonResponse:
    """Liveness probe. No DB access — must answer even if the DB is down."""
    return JsonResponse({"status": "ok"})


def readyz(request: HttpRequest) -> JsonResponse:
    """Readiness probe. Touches the DB and Redis."""
    checks: dict[str, str] = {}

    try:
        connections["default"].cursor().execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    try:
        redis_client = Redis.from_url(settings.CELERY_BROKER_URL)
        redis_client.ping()
        checks["redis"] = "ok"
    except RedisError as exc:
        checks["redis"] = f"error: {exc}"

    healthy = all(value == "ok" for value in checks.values())
    status = 200 if healthy else 503
    return JsonResponse({"status": "ok" if healthy else "error", "checks": checks}, status=status)


urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("readyz/", readyz, name="readyz"),
    path("admin/", admin.site.urls),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/", include("keel.organizations.urls")),
    path("api/v1/", include("keel.billing.urls")),
    # Headed accounts/ URLs are still required even in HEADLESS_ONLY mode:
    # the social-provider OAuth handshake redirects through them (PRD §8
    # Phase 2 A.1; allauth headless installation docs).
    path("accounts/", include("allauth.urls")),
    path("_allauth/", include("allauth.headless.urls")),
]
