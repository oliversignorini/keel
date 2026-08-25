"""Seat sync (docs/plans/phase-4.md B.5): behind ``BILLING_SEAT_PRICING``,
off by default. When on, seat count syncs to Stripe with proration on
membership create and remove, dispatched via ``transaction.on_commit()``,
never inline. When off: no Stripe call is made, and membership writes
succeed while Stripe is unreachable — "it is the reason the flag exists."
Stripe calls are monkeypatched — no real Stripe call, no stripe-mock."""

import pytest

from keel.accounts.models import User
from keel.billing import stripe_client
from keel.billing.models import Plan, Price, Subscription
from keel.billing.services import sync_seat_quantity
from keel.organizations import services
from keel.organizations.models import Membership, Organization
from keel.organizations.roles import PRESET_MEMBER, seed_preset_roles

pytestmark = pytest.mark.django_db

_counter = 0


def _user(prefix: str = "user") -> User:
    global _counter
    _counter += 1
    return User.objects.create_user(
        email=f"{prefix}-{_counter}@example.com", password="s3cret-pass"
    )


def _org_with_owner() -> tuple[Organization, User]:
    global _counter
    _counter += 1
    owner = _user("owner")
    org = services.create_organization(name="Acme", slug=f"acme-seat-{_counter}", created_by=owner)
    return org, owner


def _subscribe(org: Organization) -> Subscription:
    plan = Plan.objects.create(
        code=f"plan-{org.pk}", name="Plan", stripe_product_id=f"prod-{org.pk}"
    )
    price = Price.objects.create(
        plan=plan,
        stripe_price_id=f"price-{org.pk}",
        interval=Price.INTERVAL_MONTH,
        unit_amount=1900,
        currency="AUD",
    )
    return Subscription.objects.create(
        organization=org,
        stripe_subscription_id=f"sub-{org.pk}",
        plan=plan,
        price=price,
        status="active",
        quantity=1,
    )


# --- sync_seat_quantity (service-level) ------------------------------------


def test_sync_seat_quantity_is_a_noop_without_a_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, _owner = _org_with_owner()

    def _fail(**kw):
        raise AssertionError("must not call Stripe without a subscription")

    monkeypatch.setattr(stripe_client, "update_subscription_quantity", _fail)

    sync_seat_quantity(org)  # does not raise


def test_sync_seat_quantity_counts_only_active_memberships(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, _owner = _org_with_owner()
    subscription = _subscribe(org)
    role = seed_preset_roles()[PRESET_MEMBER]
    Membership.objects.create(
        organization=org, user=_user("m1"), role=role, status=Membership.STATUS_ACTIVE
    )
    Membership.objects.create(
        organization=org, user=_user("m2"), role=role, status=Membership.STATUS_SUSPENDED
    )
    seen = {}
    monkeypatch.setattr(stripe_client, "update_subscription_quantity", lambda **kw: seen.update(kw))

    sync_seat_quantity(org)

    # owner (active) + m1 (active); m2 is suspended and doesn't count.
    assert seen == {"subscription_id": subscription.stripe_subscription_id, "quantity": 2}
    subscription.refresh_from_db()
    assert subscription.quantity == 2


# --- wiring: accept_invitation / remove_member ------------------------------


def test_flag_off_no_stripe_call_and_membership_write_succeeds(
    settings, monkeypatch: pytest.MonkeyPatch, django_capture_on_commit_callbacks
) -> None:
    settings.BILLING_SEAT_PRICING = False
    org, owner = _org_with_owner()
    _subscribe(org)
    role = seed_preset_roles()[PRESET_MEMBER]
    invitee = _user("invitee")
    invitation = services.create_invitation(
        organization=org, email=invitee.email, role=role, invited_by=owner
    )

    def _fail(**kw):
        raise AssertionError("must not call Stripe when BILLING_SEAT_PRICING is off")

    monkeypatch.setattr(stripe_client, "update_subscription_quantity", _fail)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        membership = services.accept_invitation(invitation=invitation, user=invitee)

    # @audited registers its own on_commit callback regardless of the
    # flag — what matters is that _fail (the seat-sync Stripe call) was
    # never among them, proven by _fail not raising above.
    assert len(callbacks) == 1
    assert Membership.objects.filter(pk=membership.pk, status=Membership.STATUS_ACTIVE).exists()


def test_flag_on_syncs_on_accept_and_on_remove(
    settings, monkeypatch: pytest.MonkeyPatch, django_capture_on_commit_callbacks
) -> None:
    settings.BILLING_SEAT_PRICING = True
    org, owner = _org_with_owner()
    subscription = _subscribe(org)
    role = seed_preset_roles()[PRESET_MEMBER]
    invitee = _user("invitee")
    invitation = services.create_invitation(
        organization=org, email=invitee.email, role=role, invited_by=owner
    )
    seen = []
    monkeypatch.setattr(stripe_client, "update_subscription_quantity", lambda **kw: seen.append(kw))

    with django_capture_on_commit_callbacks(execute=True):
        membership = services.accept_invitation(invitation=invitation, user=invitee)

    assert seen == [{"subscription_id": subscription.stripe_subscription_id, "quantity": 2}]

    with django_capture_on_commit_callbacks(execute=True):
        services.remove_member(membership=membership, actor=owner)

    assert seen[-1] == {"subscription_id": subscription.stripe_subscription_id, "quantity": 1}


def test_flag_on_membership_write_succeeds_when_stripe_is_unreachable(
    settings, monkeypatch: pytest.MonkeyPatch, django_capture_on_commit_callbacks
) -> None:
    """B.5's named reason for the flag being separate from a hard
    dependency: even with it on, a Stripe outage while syncing seats must
    not roll back the membership write that already committed. The task
    shim decouples this fully — in production a failed task never
    surfaces to the request at all; ``CELERY_TASK_EAGER_PROPAGATES =
    False`` reproduces that for this synchronous test."""
    settings.BILLING_SEAT_PRICING = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    org, owner = _org_with_owner()
    _subscribe(org)
    role = seed_preset_roles()[PRESET_MEMBER]
    invitee = _user("invitee")
    invitation = services.create_invitation(
        organization=org, email=invitee.email, role=role, invited_by=owner
    )

    def _unreachable(**kw):
        raise ConnectionError("stripe is unreachable")

    monkeypatch.setattr(stripe_client, "update_subscription_quantity", _unreachable)

    with django_capture_on_commit_callbacks(execute=True):
        membership = services.accept_invitation(invitation=invitation, user=invitee)

    assert Membership.objects.filter(pk=membership.pk, status=Membership.STATUS_ACTIVE).exists()
