"""Plans, prices, subscriptions, Stripe events, and the credit ledger
(PRD §4 "Data model" and "Credits — the metered-billing primitive")."""

from django.db import models

from keel.core.models import TimestampedModel, UUIDv7PrimaryKeyModel


class Plan(UUIDv7PrimaryKeyModel, TimestampedModel):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    stripe_product_id = models.CharField(max_length=255, blank=True, default="")
    entitlements = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    def __str__(self) -> str:
        return self.code


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
        on_delete=models.CASCADE,
        related_name="credit_ledger_entries",
        db_index=True,
    )
    job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.SET_NULL,
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

    def __str__(self) -> str:
        return f"{self.organization_id}: {self.balance}"
