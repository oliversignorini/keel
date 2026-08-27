"""Entitlements (PRD §7; docs/plans/phase-4.md B.4).

``Plan.entitlements`` is shaped ``{"features": [...], "limits": {resource:
int | None}}``. A missing key in ``limits`` means that resource isn't
capped by this plan at all (unlimited) — the same as an explicit ``None``.
An organisation with no ``Subscription`` row (billing not wired up on this
project, or the org simply hasn't checked out yet) resolves to
``{"features": [], "limits": {}}``: no *feature* is granted without an
explicit plan, but no *limit* is imposed either. That asymmetry is
deliberate — feature-gating is opt-in per feature, but a project that
never turns on seat pricing (``BILLING_SEAT_PRICING`` off) must not have
every membership acceptance start failing with 402 the moment this module
exists.

Both ``check_feature``/``@requires_entitlement`` and ``check_limit`` raise
``PaymentRequired`` (402) with upgrade context in ``details``, never a
bare bool — the same reasoning ``keel.core.authz.Decision`` documents for
permission denials: a 402 body needs to say *what* is over, not just that
something is.

Per-resource usage counters are an open registry (same shape as
``keel.core.authz.PermissionRegistry``): this module only knows resource
*names*, never how to count them — knowing that would mean importing every
domain app into billing. Each owning app registers its own counter from
``AppConfig.ready()``, the same way ``organizations/apps.py`` registers
its permission guards.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any

from keel.billing.models import Subscription
from keel.core.exceptions import Conflict, PaymentRequired

_resource_counters: dict[str, Callable[[Any], int]] = {}


class UnregisteredResource(Exception):
    """A plan declares a limit for a resource nobody registered a usage
    counter for — a config error, not a runtime 402 (PRD §4 invariant 2's
    "fail loudly, not silently" reasoning applies here too)."""

    def __init__(self, resource: str) -> None:
        self.resource = resource
        super().__init__(
            f"No usage counter registered for resource {resource!r}. Register one "
            "via keel.billing.entitlements.register_resource_counter from the "
            "owning app's AppConfig.ready()."
        )


def register_resource_counter(resource: str, counter: Callable[[Any], int]) -> None:
    _resource_counters[resource] = counter


def _count_usage(organization: Any, resource: str) -> int:
    try:
        counter = _resource_counters[resource]
    except KeyError:
        raise UnregisteredResource(resource) from None
    return counter(organization)


def resolve_entitlements(organization: Any) -> dict[str, Any]:
    """Feeds ``GET /api/v1/me/`` (docs/plans/phase-4.md B.4: "Resolution
    feeds GET /api/v1/me/ ... coordinate rather than duplicating it")."""
    subscription = (
        Subscription.objects.filter(organization=organization).select_related("plan").first()
    )
    return _entitlements_from_subscription(subscription)


def resolve_entitlements_bulk(organizations: Any) -> dict[Any, dict[str, Any]]:
    """One query for every organisation's entitlements, keyed by
    ``organization_id`` — the bulk counterpart to ``resolve_entitlements``.

    ``GET /api/v1/me/`` (api-patterns finding 12) used to call
    ``resolve_entitlements`` once per organisation in a Python loop; a
    single ``organization__in`` query replaces the whole loop. An
    organisation with no row here still resolves to the same "no
    subscription" default ``resolve_entitlements`` returns, via the
    caller doing ``bulk.get(org.id, _entitlements_from_subscription(None))``.
    """
    subscriptions = Subscription.objects.filter(organization__in=organizations).select_related(
        "plan"
    )
    return {
        subscription.organization_id: _entitlements_from_subscription(subscription)
        for subscription in subscriptions
    }


def _entitlements_from_subscription(subscription: Any) -> dict[str, Any]:
    if subscription is None:
        return {"features": [], "limits": {}}
    entitlements: dict[str, Any] = subscription.plan.entitlements or {}
    return {"features": entitlements.get("features", []), "limits": entitlements.get("limits", {})}


def check_feature(organization: Any, feature: str) -> None:
    entitlements = resolve_entitlements(organization)
    if feature not in entitlements["features"]:
        raise PaymentRequired(
            code="feature_not_entitled",
            message=f"Your plan does not include {feature!r}.",
            details={"feature": feature},
        )


def requires_entitlement(feature: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Gates a service function on a feature code (docs/plans/phase-4.md
    B.4: "``@requires_entitlement('api_access')`` gates features"). The
    decorated function must be called with ``organization`` as a keyword
    argument — every service in this codebase already uses keyword-only
    arguments (PRD §4 "Where is authorization expressed?" applies the same
    "fail loudly" reasoning to a misuse of this decorator as to a missing
    permission code)."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                organization = kwargs["organization"]
            except KeyError:
                raise TypeError(
                    f"{func.__name__} is decorated with @requires_entitlement and "
                    "must be called with organization as a keyword argument."
                ) from None
            check_feature(organization, feature)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def check_limit(organization: Any, resource: str, requested: int = 1) -> None:
    """Gates a quantity (docs/plans/phase-4.md B.4: "``check_limit(org,
    'widgets')`` gates quantities"). A missing or ``None`` limit for
    ``resource`` means unlimited — see module docstring."""
    entitlements = resolve_entitlements(organization)
    limit = entitlements["limits"].get(resource)
    if limit is None:
        return
    current_usage = _count_usage(organization, resource)
    if current_usage + requested > limit:
        raise PaymentRequired(
            code="limit_exceeded",
            message=f"This would exceed your plan's {resource} limit ({limit}).",
            details={"resource": resource, "limit": limit, "current_usage": current_usage},
        )


def enforce_downgrade_limits(organization: Any, new_plan: Any) -> None:
    """Blocks a plan change that would leave current usage over the new
    plan's limits, naming what's over (docs/plans/phase-4.md B.4: "Plan
    downgrade below current usage is blocked with a message that names
    what is over")."""
    limits: dict[str, int | None] = (new_plan.entitlements or {}).get("limits", {})
    over_limit = []
    for resource, limit in limits.items():
        if limit is None:
            continue
        usage = _count_usage(organization, resource)
        if usage > limit:
            over_limit.append({"resource": resource, "usage": usage, "limit": limit})
    if over_limit:
        named = ", ".join(
            f"{row['resource']} ({row['usage']}/{row['limit']})" for row in over_limit
        )
        raise Conflict(
            code="downgrade_blocked",
            message=f"Current usage exceeds {new_plan.code}'s limits: {named}.",
            details={"over_limit": over_limit},
        )
