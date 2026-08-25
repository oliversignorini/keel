"""Checkout, portal, and subscription views (PRD §7; docs/plans/phase-4.md
B.2). Plain ``APIView``s in the ``OrganizationDetailView`` shape, not
``OrgScopedViewSet``s: each resolves ``org_slug`` and acts on *the*
subscription for that organisation — there is no separate addressable row
id in the URL for a cross-org leak to hide behind, the same reasoning
``keel.organizations.viewsets.OrganizationDetailView`` documents.
"""

import stripe
from django.http import Http404
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from keel.billing import credits, services, stripe_client, tasks
from keel.billing.models import Price, StripeEvent, Subscription
from keel.billing.serializers import (
    CheckoutRequestSerializer,
    SubscriptionSerializer,
)
from keel.core.authz import has_perm
from keel.core.exceptions import PermissionDeniedWithReason, UnprocessableEntity
from keel.organizations.models import Organization
from keel.organizations.permissions import Perm
from keel.organizations.resolvers import resolve_organization


class _OrganizationBillingView(APIView):
    permission_classes = (IsAuthenticated,)
    required_permission: str

    def _get_organization(self, request: Request, org_slug: str) -> Organization:
        organization = resolve_organization(request, org_slug)
        if organization is None:
            raise Http404
        decision = has_perm(request.user, organization, self.required_permission)
        if not decision.allowed:
            raise PermissionDeniedWithReason(
                code=decision.reason or "permission_denied", details=decision.details
            )
        return organization


class CheckoutSessionView(_OrganizationBillingView):
    """``POST /organizations/<org_slug>/billing/checkout/``."""

    required_permission = Perm.BILLING_MANAGE

    def post(self, request: Request, org_slug: str) -> Response:
        organization = self._get_organization(request, org_slug)
        serializer = CheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        price = Price.objects.filter(
            pk=serializer.validated_data["price_id"], is_active=True
        ).first()
        if price is None:
            raise UnprocessableEntity(code="price_not_found", message="Unknown or inactive price.")
        url = services.create_checkout_session(
            organization=organization,
            actor=request.user,
            impersonator=getattr(request, "impersonator", None),
            price=price,
            success_url=f"{_frontend_base()}/{organization.slug}/settings/billing?checkout=success",
            cancel_url=f"{_frontend_base()}/{organization.slug}/settings/billing?checkout=cancelled",
        )
        return Response({"url": url})


class BillingPortalView(_OrganizationBillingView):
    """``POST /organizations/<org_slug>/billing/portal/``."""

    required_permission = Perm.BILLING_MANAGE

    def post(self, request: Request, org_slug: str) -> Response:
        organization = self._get_organization(request, org_slug)
        url = services.create_portal_session(
            organization=organization,
            actor=request.user,
            impersonator=getattr(request, "impersonator", None),
            return_url=f"{_frontend_base()}/{organization.slug}/settings/billing",
        )
        return Response({"url": url})


class SubscriptionView(_OrganizationBillingView):
    """``GET /organizations/<org_slug>/billing/subscription/``."""

    required_permission = Perm.BILLING_VIEW

    def get(self, request: Request, org_slug: str) -> Response:
        organization = self._get_organization(request, org_slug)
        subscription = Subscription.objects.filter(organization=organization).first()
        if subscription is None:
            return Response({"subscription": None})
        return Response({"subscription": SubscriptionSerializer(subscription).data})


class CreditBalanceView(_OrganizationBillingView):
    """``GET /organizations/<org_slug>/billing/credits/`` (PRD §7's
    credits endpoint list; docs/plans/phase-4.md Worktree C's
    ``<CreditMeter>``, which is "rendered **only when credits are
    enabled**").

    Behind ``BILLING_CREDITS``, off by default (phase-4.md A.5: "With it
    off: no endpoints, no meter, no cost"). Off is a **404**, not a zero
    balance: the flag decides whether this feature exists at all, so the
    web meter's absence-of-data path is "there is nothing here" rather
    than "you have no credits" — two states a user would read very
    differently. 404 is also what an unresolvable organisation already
    returns from ``_get_organization``, which keeps the flag from being a
    distinguishable signal to a non-member either way.
    """

    required_permission = Perm.BILLING_VIEW

    def get(self, request: Request, org_slug: str) -> Response:
        if not credits.credits_enabled():
            raise Http404
        organization = self._get_organization(request, org_slug)
        return Response({"balance": credits.get_balance(organization)})


class StripeWebhookView(APIView):
    """``POST /api/v1/stripe/webhook/`` (PRD §6 "Stripe webhook";
    docs/plans/phase-4.md B.3). No session auth or CSRF: this is a
    server-to-server call from Stripe with no session cookie, verified by
    signature instead — DRF's ``SessionAuthentication`` only enforces CSRF
    once it has resolved a session user, which an unauthenticated request
    never does, so leaving ``authentication_classes`` empty here is belt
    and braces, not a gap.

    Records the event and acknowledges before any processing happens
    (PRD §6, "Acknowledge in under 200ms ... work happens async") — the
    only synchronous work below a signature check is one
    ``get_or_create`` and enqueuing a task.
    """

    permission_classes = (AllowAny,)
    authentication_classes = ()

    def post(self, request: Request) -> Response:
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        try:
            event = stripe_client.verify_webhook_signature(
                payload=request.body, sig_header=sig_header
            )
        except stripe.SignatureVerificationError:
            # Unsigned or wrongly-signed: 400, change nothing, no retry
            # (PRD §6) — no StripeEvent row is written for a payload that
            # never proved it came from Stripe.
            return Response(status=400)

        stripe_event, created = StripeEvent.objects.get_or_create(
            id=event["id"],
            defaults={"type": event["type"], "payload": event.to_dict()},
        )
        if created:
            tasks.dispatch_stripe_event.delay(str(stripe_event.pk))
        # Already recorded (a replay) or freshly created: either way this
        # is a 200 — idempotent no-op for a replay (PRD §6, "Already
        # processed → 200 immediately").
        return Response(status=200)


def _frontend_base() -> str:
    from django.conf import settings

    base: str = settings.APP_FRONTEND_URL
    return base.rstrip("/")
