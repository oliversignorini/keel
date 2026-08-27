from django.conf import settings
from django.contrib import admin
from django.db import connections
from django.http import HttpRequest, JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView
from redis import Redis
from redis.exceptions import RedisError

from keel.audit.views import impersonation_router as audit_impersonation_router
from keel.audit.views import router as audit_router
from keel.billing.views import plans_router as billing_plans_router
from keel.billing.views import router as billing_router
from keel.billing.views import webhook_router as billing_webhook_router
from keel.core.ninja_api import api as ninja_api
from keel.files.views import router as files_router
from keel.jobs.views import router as jobs_router
from keel.organizations.views import invite_router as org_invite_router
from keel.organizations.views import me_router as org_me_router
from keel.organizations.views import nested_router as org_nested_router
from keel.organizations.views import org_router
from keel.widgets.views import router as widgets_router

# Every app's Ninja router mounts on this one shared api instance (stage
# 10.A/10.D's note in keel/core/ninja_api.py). "/organizations" here, not
# "/orgs" — the orgs rename is stage 10.C's job, done in one sweep with
# every other route.
ninja_api.add_router("/organizations", widgets_router)
ninja_api.add_router("/organizations", audit_router)
ninja_api.add_router("", audit_impersonation_router)
ninja_api.add_router("", billing_plans_router)
ninja_api.add_router("/organizations", billing_router)
ninja_api.add_router("", billing_webhook_router)
ninja_api.add_router("/organizations", jobs_router)
ninja_api.add_router("/organizations", files_router)
ninja_api.add_router("", org_router)
ninja_api.add_router("/organizations", org_nested_router)
ninja_api.add_router("", org_me_router)
ninja_api.add_router("", org_invite_router)


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
    path("api/v1/", ninja_api.urls),
    # Headed accounts/ URLs are still required even in HEADLESS_ONLY mode:
    # the social-provider OAuth handshake redirects through them (PRD §8
    # Phase 2 A.1; allauth headless installation docs).
    path("accounts/", include("allauth.urls")),
    path("_allauth/", include("allauth.headless.urls")),
]
