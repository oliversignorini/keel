import pytest

from keel.accounts.models import User
from keel.billing.models import Plan, Price, Subscription
from keel.core.exceptions import PaymentRequired
from keel.organizations.models import Organization
from keel.widgets import services
from keel.widgets.models import Widget

pytestmark = pytest.mark.django_db


def _org() -> tuple[Organization, User]:
    creator = User.objects.create_user(email="creator@example.com", password="s3cret-pass")
    org = Organization.objects.create(name="Acme", slug="acme", created_by=creator)
    return org, creator


def test_create_widget_creates_a_row() -> None:
    org, creator = _org()

    widget = services.create_widget(
        organization=org, name="Sprocket", description="spins", status="active", created_by=creator
    )

    assert widget.pk is not None
    assert Widget.objects.filter(pk=widget.pk, organization=org).exists()


def test_create_widget_enforces_the_widgets_limit() -> None:
    org, creator = _org()
    plan = Plan.objects.create(
        code="starter",
        name="Starter",
        stripe_product_id="prod_starter",
        entitlements={"features": [], "limits": {"widgets": 1}},
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
    services.create_widget(
        organization=org, name="First", description="", status="", created_by=creator
    )

    with pytest.raises(PaymentRequired) as exc_info:
        services.create_widget(
            organization=org, name="Second", description="", status="", created_by=creator
        )

    assert exc_info.value.code == "limit_exceeded"


def test_update_widget_updates_only_given_fields() -> None:
    org, creator = _org()
    widget = services.create_widget(
        organization=org, name="Sprocket", description="", status="", created_by=creator
    )

    updated = services.update_widget(widget=widget, actor=creator, status="archived")

    updated.refresh_from_db()
    assert updated.status == "archived"
    assert updated.name == "Sprocket"


def test_delete_widget_removes_the_row() -> None:
    org, creator = _org()
    widget = services.create_widget(
        organization=org, name="Sprocket", description="", status="", created_by=creator
    )

    services.delete_widget(widget=widget, actor=creator)

    assert not Widget.objects.filter(pk=widget.pk).exists()
