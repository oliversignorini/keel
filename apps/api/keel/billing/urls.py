"""URL wiring for billing (PRD §7; docs/plans/phase-4.md B.1, B.2)."""

from django.urls import path
from rest_framework.routers import SimpleRouter

from keel.billing import views, viewsets

router = SimpleRouter(trailing_slash=True)
router.register("plans", viewsets.PlanViewSet, basename="plan")

urlpatterns = [
    *router.urls,
    path("stripe/webhook/", views.StripeWebhookView.as_view(), name="stripe-webhook"),
    path(
        "organizations/<slug:org_slug>/billing/checkout/",
        views.CheckoutSessionView.as_view(),
        name="billing-checkout",
    ),
    path(
        "organizations/<slug:org_slug>/billing/portal/",
        views.BillingPortalView.as_view(),
        name="billing-portal",
    ),
    path(
        "organizations/<slug:org_slug>/billing/subscription/",
        views.SubscriptionView.as_view(),
        name="billing-subscription",
    ),
    path(
        "organizations/<slug:org_slug>/billing/credits/",
        views.CreditBalanceView.as_view(),
        name="billing-credits",
    ),
]
