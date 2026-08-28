import pytest

from keel.__app__ import services
from keel.__app__.models import __Resource__
from keel.accounts.models import User
from keel.billing.models import Plan, Price, Subscription
from keel.core.exceptions import PaymentRequired
from keel.organizations.models import Organization

# keel:insert service_test_imports

pytestmark = pytest.mark.django_db


def _org() -> tuple[Organization, User]:
    creator = User.objects.create_user(email="creator@example.com", password="s3cret-pass")
    org = Organization.objects.create(name="Acme", slug="acme", created_by=creator)
    return org, creator


def test_create___resource___creates_a_row() -> None:
    org, creator = _org()

    row = services.create___resource__(
        organization=org,
        actor=creator,
        # keel:insert service_call_kwargs
    )

    assert row.pk is not None
    assert __Resource__.objects.filter(pk=row.pk, organization=org).exists()


def test_create___resource___enforces_the___app___limit() -> None:
    """CLAUDE.md invariant 3's ordering, proved: ``check_limit`` runs
    before anything is written, so the second create raises rather than
    inserting a row and rolling it back."""
    org, creator = _org()
    plan = Plan.objects.create(
        code="starter",
        name="Starter",
        stripe_product_id="prod_starter",
        entitlements={"features": [], "limits": {"__app__": 1}},
    )
    price = Price.objects.create(
        plan=plan,
        stripe_price_id="price_starter",
        interval=Price.INTERVAL_MONTH,
        unit_amount=1900,
        currency="AUD",
    )
    Subscription.objects.create(
        organization=org,
        stripe_subscription_id="sub_starter",
        plan=plan,
        price=price,
        status="active",
    )
    services.create___resource__(
        organization=org,
        actor=creator,
        # keel:insert service_call_kwargs
    )

    with pytest.raises(PaymentRequired) as exc_info:
        services.create___resource__(
            organization=org,
            actor=creator,
            # keel:insert service_call_kwargs
        )

    assert exc_info.value.code == "limit_exceeded"


def test_update___resource___updates_only_given_fields() -> None:
    org, creator = _org()
    row = services.create___resource__(
        organization=org,
        actor=creator,
        # keel:insert service_call_kwargs
    )

    # keel:insert update_assertions


def test_delete___resource___removes_the_row() -> None:
    org, creator = _org()
    row = services.create___resource__(
        organization=org,
        actor=creator,
        # keel:insert service_call_kwargs
    )

    deleted = services.delete___resource__(__resource__=row, actor=creator)

    assert not __Resource__.objects.filter(pk=row.pk).exists()
    # Returned, pk intact, so the @audited row names what was deleted —
    # a delete service returning None records a blank target.
    assert deleted.pk == row.pk
    assert deleted.organization_id == org.pk
