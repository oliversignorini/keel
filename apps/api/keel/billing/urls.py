"""URL wiring for billing (PRD §7; docs/plans/phase-4.md B.1)."""

from rest_framework.routers import SimpleRouter

from keel.billing import viewsets

router = SimpleRouter(trailing_slash=True)
router.register("plans", viewsets.PlanViewSet, basename="plan")

urlpatterns = router.urls
