"""Plans, prices, subscriptions, Stripe events, and the credit ledger
(PRD §4 "Data model" and "Credits — the metered-billing primitive")."""

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

from keel.core.models import TimestampedModel, UUIDv7PrimaryKeyModel


class EntitlementsSpec(BaseModel):
    """The schema ``Plan.entitlements`` is documented as (ddia#24):
    ``{"features": [...], "limits": {resource: int | None}, "daily_credit_cap":
    int | None}``. Validated here — a typo'd top-level key (e.g.
    ``"limmits"``) is rejected at save time instead of silently doing
    nothing wherever it's read. Deliberately does *not* check that
    ``limits`` keys are registered resources: a plan may legitimately
    reference a resource before (or without) the owning app registering a
    counter for it — ``check_limit`` is where an unregistered resource
    *name* is the failure, not here (entitlements.py's
    ``UnregisteredResource``)."""

    model_config = ConfigDict(extra="forbid")

    features: list[str] = []
    limits: dict[str, int | None] = {}
    daily_credit_cap: int | None = None


class Plan(UUIDv7PrimaryKeyModel, TimestampedModel):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    stripe_product_id = models.CharField(max_length=255, blank=True, default="")
    entitlements = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    def __str__(self) -> str:
        return self.code

    def clean(self) -> None:
        super().clean()
        try:
            EntitlementsSpec.model_validate(self.entitlements or {})
        except PydanticValidationError as exc:
            raise ValidationError({"entitlements": str(exc)}) from exc

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.clean()
        super().save(*args, **kwargs)


class Price(UUIDv7PrimaryKeyModel, TimestampedModel):
    INTERVAL_MONTH = "month"
    INTERVAL_YEAR = "year"
    INTERVAL_CHOICES = (
        (INTERVAL_MONTH, "Month"),
        (INTERVAL_YEAR, "Year"),
    )

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="prices")
    stripe_price_id = models.CharField(max_length=255, unique=True)
    interval = models.CharField(max_length=8, choices=INTERVAL_CHOICES)
    unit_amount = models.IntegerField()
    currency = models.CharField(max_length=3, default="AUD")
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.stripe_price_id


class Subscription(UUIDv7PrimaryKeyModel, TimestampedModel):
    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.CASCADE, related_name="subscription"
    )
    stripe_subscription_id = models.CharField(max_length=255, unique=True)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    price = models.ForeignKey(Price, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=32)
    quantity = models.IntegerField(default=1)
    current_period_end = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    stripe_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "The originating Stripe event's `created` timestamp (ddia#9) — "
            "an LWW version guard. A webhook write only applies when its "
            "event is newer than the one that wrote this row last, so an "
            "out-of-order redelivery can't resurrect a stale status."
        ),
    )

    def __str__(self) -> str:
        return self.stripe_subscription_id


class StripeEvent(models.Model):
    """id is the Stripe event id itself — idempotency depends on it being
    the primary key, not a surrogate UUID (PRD §4, task 1.10)."""

    id = models.CharField(max_length=255, primary_key=True)
    type = models.CharField(max_length=255)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return self.id


class CreditLedgerEntry(UUIDv7PrimaryKeyModel):
    """Append-only. Never updated, never deleted — enforced by service
    discipline (invariant 7 forbids database triggers), not the schema."""

    KIND_GRANT = "grant"
    KIND_HOLD = "hold"
    KIND_CONSUME = "consume"
    KIND_RELEASE = "release"
    KIND_REFUND = "refund"
    KIND_ADJUSTMENT = "adjustment"
    KIND_CHOICES = (
        (KIND_GRANT, "plan allowance or purchased top-up"),
        (KIND_HOLD, "negative, reserved at job creation"),
        (KIND_CONSUME, "negative, settles a hold on completion"),
        (KIND_RELEASE, "positive, unused portion of a hold"),
        (KIND_REFUND, "positive, job failed"),
        (KIND_ADJUSTMENT, "operator correction; reason required"),
    )

    organization = models.ForeignKey(
        "organizations.Organization",
        # ddia#5/#23: PROTECT, not CASCADE — an append-only financial
        # record must outlive the organisation row it references.
        # Organisations are soft-deleted (Organization.deleted_at) in this
        # codebase's own service layer, so nothing here ever hits this
        # protection in normal operation; it only stops a hard delete
        # (admin, a script) from silently erasing the ledger.
        on_delete=models.PROTECT,
        related_name="credit_ledger_entries",
        db_index=True,
    )
    job = models.ForeignKey(
        "jobs.Job",
        # ddia#5/#23: PROTECT, not SET_NULL — severing the link between a
        # hold and the job it paid for makes after-the-fact reconciliation
        # of holds-to-settlements impossible. null=True is unrelated to
        # this: a hold/consume/grant/adjustment may simply have no job.
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="credit_ledger_entries",
    )
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    amount = models.IntegerField()
    reason = models.TextField(blank=True, default="")
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_ledger_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = (models.Index(fields=["organization", "created_at"]),)
        constraints = (
            # ddia#5/#23: kind decides amount's sign — a hold/consume can
            # never be storable as a credit, nor a grant/release/refund as
            # a debit. adjustment is the one kind allowed either sign
            # (credits.adjust already rejects zero at the service layer;
            # this constraint is the database-level backstop for every
            # other write path, including a future one that forgets).
            models.CheckConstraint(
                # Nested classes don't see the enclosing class body's
                # namespace, so KIND_* is spelled out as literals here
                # rather than referencing CreditLedgerEntry.KIND_HOLD etc.
                condition=(
                    (models.Q(kind__in=("hold", "consume")) & models.Q(amount__lt=0))
                    | (models.Q(kind__in=("grant", "release", "refund")) & models.Q(amount__gt=0))
                    | (models.Q(kind="adjustment") & ~models.Q(amount=0))
                ),
                name="creditledgerentry_kind_amount_sign",
            ),
        )
        # Django admin's default pluralisation just appends "s"
        # ("Credit ledger entrys" — docs/plans/phase-8.md 8.8).
        verbose_name_plural = "Credit ledger entries"

    def __str__(self) -> str:
        return f"{self.kind} {self.amount} @ {self.organization_id}"


class CreditBalance(models.Model):
    """One-to-one with Organization; the FK *is* the primary key —
    ``SELECT ... FOR UPDATE`` on this row serialises concurrent holds
    (PRD §4, task 1.10). The ledger is the truth; this is an index."""

    organization = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="credit_balance",
    )
    balance = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = (
            # ddia#5/#23: the index can never say a negative balance —
            # service discipline (`credits._debit`'s affordability check)
            # is what's supposed to guarantee this; the constraint is what
            # makes it true regardless of which code path wrote the row.
            models.CheckConstraint(
                condition=models.Q(balance__gte=0), name="creditbalance_balance_gte_zero"
            ),
        )

    def __str__(self) -> str:
        return f"{self.organization_id}: {self.balance}"
