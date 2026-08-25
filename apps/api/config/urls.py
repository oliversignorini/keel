from django.conf import settings
from django.db import connections
from django.http import HttpRequest, JsonResponse
from django.urls import path
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
    except Exception as exc:  # noqa: BLE001 - readiness probe reports any failure
        checks["database"] = f"error: {exc}"

    try:
        redis_client = Redis.from_url(settings.CELERY_BROKER_URL)
        redis_client.ping()
        checks["redis"] = "ok"
    except RedisError as exc:
        checks["redis"] = f"error: {exc}"

    healthy = all(value == "ok" for value in checks.values())
    return JsonResponse({"status": "ok" if healthy else "error", "checks": checks}, status=200 if healthy else 503)


urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("readyz/", readyz, name="readyz"),
]
