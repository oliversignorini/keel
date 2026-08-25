"""``keel.billing.entitlements`` (docs/plans/phase-4.md B.4)."""

import pytest

from keel.accounts.models import User
from keel.billing import entitlements
from keel.billing.entitlements import (
    UnregisteredResource,
    check_feature,
    check_limit,
    enforce_downgrade_limits,
    requires_entitlement,
    resolve_entitlements,
)
from keel.billing.models import Plan, Price, Subscription
from keel.core.exceptions import Conflict, PaymentRequired
from keel.organizations.models import Organization

pytestmark = pytest.mark.django_db


def _org() -> Organization:
    creator = User.objects.create_user(email="owner-ent@example.com", password="s3cret-pass")
    return Organization.objects.create(
        name="Acme", slug="acme-ent", created_by=creator, stripe_customer_id="cus_ent"
    )


def _plan_with_entitlements(entitlements: dict, code: str = "starter") -> Plan:
    return Plan.objects.create(
        code=code, name=code.title(), stripe_product_id=f"prod_{code}", entitlements=entitlements
    )


def _subscribe(org: Organization, plan: Plan) -> Subscription:
    price = Price.objects.create(
        plan=plan,
        stripe_price_id=f"price_{plan.code}",
        interval=Price.INTERVAL_MONTH,
        unit_amount=1900,
        currency="AUD",
    )
    return Subscription.objects.create(
        organization=org,
        stripe_subscription_id=f"sub_{plan.code}",
        plan=plan,
        price=price,
        status="active",
    )


# --- resolve_entitlements -------------------------------------------------


def test_resolve_entitlements_defaults_to_empty_when_no_subscription() -> None:
    org = _org()

    assert resolve_entitlements(org) == {"features": [], "limits": {}}


def test_resolve_entitlements_reads_the_current_plan() -> None:
    org = _org()
    plan = _plan_with_entitlements({"features": ["api_access"], "limits": {"seats": 5}})
    _subscribe(org, plan)

    assert resolve_entitlements(org) == {"features": ["api_access"], "limits": {"seats": 5}}


# --- check_feature / requires_entitlement --------------------------------


def test_check_feature_allows_when_entitled() -> None:
    org = _org()
    plan = _plan_with_entitlements({"features": ["api_access"]})
    _subscribe(org, plan)

    check_feature(org, "api_access")  # does not raise


def test_check_feature_raises_payment_required_when_not_entitled() -> None:
    org = _org()

    with pytest.raises(PaymentRequired) as exc_info:
        check_feature(org, "api_access")

    assert exc_info.value.code == "feature_not_entitled"
    assert exc_info.value.details == {"feature": "api_access"}


def test_requires_entitlement_decorator_gates_a_service_function() -> None:
    org = _org()
    plan = _plan_with_entitlements({"features": ["api_access"]})
    _subscribe(org, plan)

    @requires_entitlement("api_access")
    def call_api(*, organization):
        return "ok"

    assert call_api(organization=org) == "ok"


def test_requires_entitlement_decorator_denies_without_the_feature() -> None:
    org = _org()

    @requires_entitlement("api_access")
    def call_api(*, organization):
        return "ok"

    with pytest.raises(PaymentRequired):
        call_api(organization=org)


def test_requires_entitlement_decorator_requires_organization_kwarg() -> None:
    @requires_entitlement("api_access")
    def call_api(organization):
        return "ok"

    with pytest.raises(TypeError):
        call_api(_org())


# --- check_limit -----------------------------------------------------------


def test_check_limit_allows_when_no_limit_configured() -> None:
    org = _org()

    check_limit(org, "seats")  # no subscription at all: unlimited by default


def test_check_limit_allows_when_limit_is_explicitly_none() -> None:
    org = _org()
    plan = _plan_with_entitlements({"limits": {"seats": None}})
    _subscribe(org, plan)

    check_limit(org, "seats")


def test_check_limit_raises_payment_required_when_over(monkeypatch: pytest.MonkeyPatch) -> None:
    org = _org()
    plan = _plan_with_entitlements({"limits": {"seats": 2}})
    _subscribe(org, plan)
    monkeypatch.setitem(entitlements._resource_counters, "seats", lambda organization: 2)

    with pytest.raises(PaymentRequired) as exc_info:
        check_limit(org, "seats")

    assert exc_info.value.code == "limit_exceeded"
    assert exc_info.value.details == {"resource": "seats", "limit": 2, "current_usage": 2}


def test_check_limit_allows_when_under(monkeypatch: pytest.MonkeyPatch) -> None:
    org = _org()
    plan = _plan_with_entitlements({"limits": {"seats": 5}})
    _subscribe(org, plan)
    monkeypatch.setitem(entitlements._resource_counters, "seats", lambda organization: 1)

    check_limit(org, "seats")  # 1 + 1 requested <= 5


def test_check_limit_raises_unregistered_resource_for_an_unknown_resource() -> None:
    org = _org()
    plan = _plan_with_entitlements({"limits": {"some_new_resource": 10}})
    _subscribe(org, plan)

    with pytest.raises(UnregisteredResource):
        check_limit(org, "some_new_resource")


# --- enforce_downgrade_limits ----------------------------------------------


def test_enforce_downgrade_limits_allows_when_under(monkeypatch: pytest.MonkeyPatch) -> None:
    org = _org()
    new_plan = _plan_with_entitlements({"limits": {"seats": 5}}, code="basic")
    monkeypatch.setitem(entitlements._resource_counters, "seats", lambda organization: 2)

    enforce_downgrade_limits(org, new_plan)  # does not raise


def test_enforce_downgrade_limits_blocks_and_names_whats_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org = _org()
    new_plan = _plan_with_entitlements({"limits": {"seats": 2, "widgets": 100}}, code="basic")
    monkeypatch.setitem(entitlements._resource_counters, "seats", lambda organization: 5)
    monkeypatch.setitem(entitlements._resource_counters, "widgets", lambda organization: 10)

    with pytest.raises(Conflict) as exc_info:
        enforce_downgrade_limits(org, new_plan)

    assert exc_info.value.code == "downgrade_blocked"
    assert "seats" in exc_info.value.message
    assert exc_info.value.details == {"over_limit": [{"resource": "seats", "usage": 5, "limit": 2}]}
