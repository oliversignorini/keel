"""Checkout, portal, and subscription views (PRD §7; docs/plans/phase-4.md
B.2). Plain ``APIView``s in the ``OrganizationDetailView`` shape, not
``OrgScopedViewSet``s: each resolves ``org_slug`` and acts on *the*
subscription for that organisation — there is no separate addressable row
id in the URL for a cross-org leak to hide behind, the same reasoning
``keel.organizations.viewsets.OrganizationDetailView`` documents.
"""

from django.http import Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from keel.billing import services
from keel.billing.models import Price, Subscription
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
            price=price,
            success_url=f"{_frontend_base()}/app/{organization.slug}/settings/billing?checkout=success",
            cancel_url=f"{_frontend_base()}/app/{organization.slug}/settings/billing?checkout=cancelled",
        )
        return Response({"url": url})


class BillingPortalView(_OrganizationBillingView):
    """``POST /organizations/<org_slug>/billing/portal/``."""

    required_permission = Perm.BILLING_MANAGE

    def post(self, request: Request, org_slug: str) -> Response:
        organization = self._get_organization(request, org_slug)
        url = services.create_portal_session(
            organization=organization,
            return_url=f"{_frontend_base()}/app/{organization.slug}/settings/billing",
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


def _frontend_base() -> str:
    from django.conf import settings

    base: str = settings.FRONTEND_URL
    return base.rstrip("/")
