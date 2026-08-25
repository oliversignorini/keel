"""Billing viewsets (PRD §7; docs/plans/phase-4.md B.1)."""

from typing import Any

from django.db.models import Prefetch
from rest_framework import mixins
from rest_framework.permissions import AllowAny

from keel.billing.models import Plan, Price
from keel.billing.serializers import PlanSerializer
from keel.core.authz import GlobalViewSet
from keel.organizations.permissions import Perm


class PlanViewSet(mixins.ListModelMixin, GlobalViewSet):
    """``GET /api/v1/plans/`` — the pricing page reads this unauthenticated
    (docs/plans/phase-4.md B.1), so it is a ``GlobalViewSet`` rather than an
    ``OrgScopedViewSet``: a plan is not owned by any organisation, and
    unlike ``OrgScopedViewSet`` requests it never resolves ``org_slug``.

    ``required_permissions`` is declared (``GlobalViewSet`` requires a
    non-empty value at import time) but not enforced here — enforcement is
    ``HasOrgPermission``, which only ``OrgScopedViewSet`` wires in.
    ``permission_classes`` is overridden to ``AllowAny`` instead, which is
    the actual gate for this endpoint. The declared code documents what an
    authenticated billing surface would require if this list were ever
    moved behind a login.
    """

    queryset = Plan.objects.filter(is_active=True).order_by("sort_order", "code")
    serializer_class = PlanSerializer
    permission_classes = (AllowAny,)
    # Unpaginated: this is a small, bounded reference table (a handful of
    # plans), and the default CursorPagination orders by its own
    # ``ordering`` attribute regardless of the queryset's — pagination
    # would silently discard the sort_order/code ordering below, which is
    # exactly the order the pricing page needs (docs/plans/phase-4.md B.1).
    pagination_class = None
    organization_scoped = False
    required_permissions = (Perm.BILLING_VIEW,)
    GLOBAL_JUSTIFICATION = (
        "Plans and prices are catalogue data, not tenant data: every "
        "organisation sees the same list, the pricing page reads it before "
        "anyone has signed in or picked an organisation, and Stripe — not "
        "this table — is the source of truth for what a plan is. There is "
        "no per-organisation row here to leak; the only thing scoped to an "
        "organisation is which plan it has subscribed to, which lives on "
        "Subscription and is reached through an OrgScopedViewSet, not this "
        "one."
    )

    def get_queryset(self) -> Any:
        active_prices = Prefetch(
            "prices",
            queryset=Price.objects.filter(is_active=True).order_by("interval"),
            to_attr="active_prices",
        )
        return super().get_queryset().prefetch_related(active_prices)
