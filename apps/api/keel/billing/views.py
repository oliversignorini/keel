"""Billing views (PRD §7; docs/plans/phase-4.md B.1, B.2, B.3; phase-10.md
10.C). ``CheckoutSessionView``/``BillingPortalView``/``SubscriptionView``/
``CreditBalanceView`` resolve ``org_slug`` and act on *the* subscription
for that organisation directly via ``resolve_and_authorize`` — there is
no separate addressable row id in the URL for a cross-org leak to hide
behind (the same reasoning ``keel.organizations.views.organization_detail``
documents), so none of these is an ``OrgScopedResource``.

``GET /api/v1/plans/`` (PRD §7's "three allowed changes", phase-10.md):
now cursor-paginated like every other collection, ordered
``(sort_order, code)`` — ``code`` is unique, so that ordering is a valid
total order for ``CursorPaginator`` (see its module docstring on why the
tuple must end in a unique tiebreaker). It stops being the one
unpaginated collection PRD §7 calls out as a deviation.
"""

from typing import Any

import stripe
from django.db.models import Prefetch
from django.http import Http404, HttpRequest, HttpResponse
from ninja import Router

from keel.billing import credits, services, stripe_client, tasks
from keel.billing.models import Plan, Price, StripeEvent, Subscription
from keel.billing.schemas import CheckoutIn, PlanOut, SubscriptionOut
from keel.core.exceptions import UnprocessableEntity
from keel.core.ninja_authz import GlobalResource, keel_router, resolve_and_authorize
from keel.core.ninja_pagination import Page, paginate
from keel.organizations.permissions import Perm

# --- Plans: public, no auth ------------------------------------------------

plans_router = Router(auth=None)


class PlanResource(GlobalResource):
    """``GET /api/v1/plans/`` — the pricing page reads this
    unauthenticated (docs/plans/phase-4.md B.1), so this is a
    ``GlobalResource`` with a public router rather than
    ``resolve_and_authorize``'s session-authenticated path: a plan is not
    owned by any organisation, and this request never resolves
    ``org_slug``.

    ``required_permissions`` is declared (``GlobalResource`` requires a
    non-empty value at import time) but not enforced — the router's
    ``auth=None`` is the actual gate. The declared code documents what an
    authenticated billing surface would require if this list were ever
    moved behind a login.
    """

    router = plans_router
    organization_scoped = False
    required_permissions = (Perm.BILLING_VIEW,)
    GLOBAL_JUSTIFICATION = (
        "Plans and prices are catalogue data, not tenant data: every "
        "organisation sees the same list, the pricing page reads it before "
        "anyone has signed in or picked an organisation, and Stripe — not "
        "this table — is the source of truth for what a plan is. There is "
        "no per-organisation row here to leak; the only thing scoped to an "
        "organisation is which plan it has subscribed to, which lives on "
        "Subscription and is reached through an OrgScopedResource, not this "
        "one."
    )


@plans_router.get("/plans/", response=Page[PlanOut], operation_id="listPlans")
def list_plans(request: HttpRequest, cursor: str | None = None, limit: int | None = None) -> dict:
    active_prices = Prefetch(
        "prices",
        queryset=Price.objects.filter(is_active=True).order_by("interval"),
        to_attr="active_prices",
    )
    queryset = (
        Plan.objects.filter(is_active=True)
        .order_by("sort_order", "code")
        .prefetch_related(active_prices)
    )
    return paginate(request, queryset, ordering=("sort_order", "code"))


# --- Checkout / portal / subscription / credits: session-authenticated ----

router = keel_router(tags=["billing"])


def _frontend_base() -> str:
    from django.conf import settings

    base: str = settings.APP_FRONTEND_URL
    return base.rstrip("/")


@router.post("/{org_slug}/billing/checkout/", operation_id="createCheckoutSession")
def create_checkout_session(request: Any, org_slug: str, payload: CheckoutIn) -> dict:
    organization = resolve_and_authorize(request, org_slug, (Perm.BILLING_MANAGE,))
    price = Price.objects.filter(pk=str(payload.price_id), is_active=True).first()
    if price is None:
        raise UnprocessableEntity(code="price_not_found", message="Unknown or inactive price.")
    url = services.create_checkout_session(
        organization=organization,
        actor=request.auth,
        impersonator=getattr(request, "impersonator", None),
        price=price,
        success_url=f"{_frontend_base()}/{organization.slug}/settings/billing?checkout=success",
        cancel_url=f"{_frontend_base()}/{organization.slug}/settings/billing?checkout=cancelled",
    )
    return {"url": url}


@router.post("/{org_slug}/billing/portal/", operation_id="createBillingPortalSession")
def create_billing_portal_session(request: Any, org_slug: str) -> dict:
    organization = resolve_and_authorize(request, org_slug, (Perm.BILLING_MANAGE,))
    url = services.create_portal_session(
        organization=organization,
        actor=request.auth,
        impersonator=getattr(request, "impersonator", None),
        return_url=f"{_frontend_base()}/{organization.slug}/settings/billing",
    )
    return {"url": url}


@router.get("/{org_slug}/billing/subscription/", operation_id="getSubscription")
def get_subscription(request: Any, org_slug: str) -> dict:
    organization = resolve_and_authorize(request, org_slug, (Perm.BILLING_VIEW,))
    subscription = Subscription.objects.filter(organization=organization).first()
    if subscription is None:
        return {"subscription": None}
    return {"subscription": SubscriptionOut.from_orm(subscription).dict()}


@router.get("/{org_slug}/billing/credits/", operation_id="getCreditBalance")
def get_credit_balance(request: Any, org_slug: str) -> dict:
    """Behind ``BILLING_CREDITS``, off by default (phase-4.md A.5). Off is
    a **404**, not a zero balance — see the DRF-era docstring this
    replaces for the full reasoning; unchanged here."""
    if not credits.credits_enabled():
        raise Http404
    organization = resolve_and_authorize(request, org_slug, (Perm.BILLING_VIEW,))
    return {"balance": credits.get_balance(organization)}


# --- Stripe webhook: public, signature-verified, CSRF-exempt --------------
# django-ninja views are always csrf_exempt at the Django middleware level
# (see keel/core/ninja_api.py's module docstring) — this router's `auth=None`
# is what keeps it session-independent, matching DRF's own
# `authentication_classes = ()` + `permission_classes = (AllowAny,)`.

webhook_router = Router(auth=None)


@webhook_router.post("/stripe/webhook/", operation_id="stripeWebhook")
def stripe_webhook(request: HttpRequest) -> HttpResponse:
    """PRD §6 "Stripe webhook": acknowledge in under 200ms, work happens
    async. The only synchronous work below a signature check is one
    ``get_or_create`` and enqueuing a task."""
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    try:
        event = stripe_client.verify_webhook_signature(payload=request.body, sig_header=sig_header)
    except stripe.SignatureVerificationError:
        # Unsigned or wrongly-signed: 400, change nothing, no retry (PRD
        # §6) — no StripeEvent row is written for a payload that never
        # proved it came from Stripe.
        return HttpResponse(status=400)

    stripe_event, created = StripeEvent.objects.get_or_create(
        id=event["id"],
        defaults={"type": event["type"], "payload": event.to_dict()},
    )
    if created or stripe_event.processed_at is None:
        # Re-enqueue on every unprocessed replay, not just on first sight
        # (ddia#7): if the row committed but the first .delay() never
        # reached the broker, `created` is False forever on redelivery and
        # the event would otherwise sit unprocessed with no way to
        # recover. Safe because process_stripe_event is a no-op on an
        # event it has already processed.
        tasks.dispatch_stripe_event.delay(str(stripe_event.pk))
    # Already processed, freshly created, or re-enqueued above: either way
    # this is a 200 — idempotent no-op for a replay (PRD §6, "Already
    # processed → 200 immediately").
    return HttpResponse(status=200)
