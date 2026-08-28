# Billing

How a product built on Keel plugs into `keel/billing/`: what a credit
means, how to add a plan, how to meter an operation, how to gate a
feature on an entitlement. See `docs/architecture.md` for the
design rationale; this file is the how-to a Keel consumer actually needs.

---

## What already exists, generic by construction

`keel/billing/` ships plans, prices, Stripe checkout/portal, webhook
handling, seat sync, and an optional credit ledger. None of it names a
product. `Plan.entitlements` is a JSON blob a project fills in; the
ledger doesn't know what a credit buys; `BILLING_CREDITS` and
`BILLING_SEAT_PRICING` are both off by default so a project that doesn't
need one of these mechanisms never pays for it.

An audit of this module found nothing product-specific left in the
diff — no hard-coded plan tiers, no assumption about what a credit is
for, no organisation-vs-user ambiguity. What it _did_ find were gaps
that made the generic machinery unsafe under concurrency and Stripe's
actual delivery guarantees; those are fixed here (see "Hardening" below)
rather
than left as sharp edges a consuming project would hit first.

## Ownership: credits belong to the organisation, never the user

Every ledger write takes an `organization`, never a `user` —
`CreditLedgerEntry.organization` and `CreditBalance.organization` are the
only FKs that matter for "whose credits are these." `actor` records _who
performed the write_ (for the audit trail), not who owns the balance.

This holds under impersonation too: `create_checkout_session` and
`create_portal_session` both call `forbid_when_impersonating` before
touching Stripe, so an impersonating operator cannot start, change, or
cancel a subscription while impersonating — the one write path where
"acting as the user" and "acting as the organisation" could be confused
is closed off entirely rather than trusted to resolve correctly.

## Defining what a credit means

Nothing in `keel/billing/` decides what a credit buys. A project defines
that by choosing what calls `credits.hold`/`consume` and for how much:

```python
# keel/rendering/services.py
from keel.billing import credits

def start_render(*, organization, job, actor):
    estimated_cost = 15  # whatever your product's pricing model says
    credits.hold(organization, estimated_cost, job=job, actor=actor)
    ...
```

A two-phase job (reserve, then settle) uses `hold` at creation and
`release`/`refund` at completion — see `keel/jobs/runner.py`'s
`_settle_credits` for the reference shape. A cost known synchronously
with nothing to reserve uses `consume` directly. Both raise
`PaymentRequired` (402) when the balance (or the daily cap, if the plan
sets one) can't cover the amount — that's the enforcement point; there
is no separate "can they afford this" check to remember to call first.

## Adding a plan

Plans and prices are normally seeded from Stripe
(`python manage.py sync_stripe_plans`, scheduled nightly by beat) — set a
`code` metadata key on the Stripe Product, and `Plan.code`/`name` sync
automatically. `Plan.entitlements` is not synced from Stripe; set it
directly (Django admin, a data migration, or a management command in
your project):

```python
Plan.objects.filter(code="pro").update(
    entitlements={
        "features": ["api_access", "custom_roles"],
        "limits": {"seats": 25, "widgets": None},  # None = not capped
        "daily_credit_cap": 500,  # only meaningful with BILLING_CREDITS on
    }
)
```

The shape is validated on save (`keel.billing.models.EntitlementsSpec`):
an unknown top-level key or a non-integer limit value raises
`ValidationError` immediately, in the admin or from a script, rather than
silently doing nothing the first time something reads it.

## Gating a feature

```python
from keel.billing.entitlements import requires_entitlement

@requires_entitlement("api_access")
def call_external_api(*, organization, ...):
    ...
```

`organization` must be a keyword argument — every service in this
codebase is keyword-only, and the decorator raises `TypeError` rather
than silently skipping the check if it isn't. On the client,
`GET /api/v1/me/` returns each organisation's resolved
`entitlements.features` list; the client renders from that, but the
decorator above is the actual enforcement point (PRD §7: "The client
renders from the permission and entitlement lists in `/me`. It is never
the enforcement point.").

## Metering a quantity

```python
from keel.billing.entitlements import check_limit

def create_widget(*, organization, ...):
    check_limit(organization, "widgets")
    ...
```

`check_limit` needs a usage counter registered for the resource name —
register one from your app's `AppConfig.ready()`, the same way
`keel/widgets/apps.py` and `keel/organizations/apps.py` do:

```python
# keel/widgets/apps.py
def ready(self):
    from keel.billing.entitlements import register_resource_counter
    from keel.widgets.models import Widget

    register_resource_counter(
        "widgets",
        lambda organization: Widget.objects.filter(organization=organization).count(),
    )
```

Three distinguishable outcomes, not two: a plan's `limits` dict can
explicitly set a resource to `None` (deliberately uncapped — allowed),
omit it entirely (also uncapped, on the same "not every plan restricts
every resource" reasoning), or the `resource` argument passed to
`check_limit` can simply not be a registered counter — a typo, or a
resource nobody's wired a counter for yet. Only the third case is a bug,
and it raises `UnregisteredResource` (a config error) regardless of what
the plan's `limits` dict says, rather than being indistinguishable from
"not capped" the way it used to be.

## Enabling credits

`BILLING_CREDITS=False` by default. The models and `credits.py`'s
arithmetic exist regardless of the flag; enabling credits is a settings
change, not a migration. With the flag off, `GET
/orgs/{slug}/billing/credits/` 404s — endpoint _absent_, not an endpoint
returning a zero balance — tested both ways in
`keel/billing/tests/test_credits_view.py`.

## Enabling seat pricing

`BILLING_SEAT_PRICING=False` by default, for the same reason: a
single-tenant-per-user project has no seats to price, and seat sync
running on every membership write for such a project is code that does
nothing useful and can still fail. Turn it on for any project with an
invite flow that matters — see `docs/architecture.md` for the design
rationale.

---

## Hardening

The audit's other finding: the generic machinery above was correct in
the average case and unsafe at the edges Stripe and concurrent access
actually exercise. Fixed here, all covered by tests:

- **Concurrent holds race to zero correctly** — `SELECT ... FOR UPDATE`
  on `CreditBalance` serialises every debit for an organisation through
  one lock (`keel/billing/tests/test_concurrency.py` proves it with real
  threads, not a simulation).
- **The ledger can no longer represent an impossible state at the
  database level** — `CreditBalance.balance` has `CHECK (balance >= 0)`;
  `CreditLedgerEntry` has a `CHECK` tying `kind` to `amount`'s sign
  (a `hold` can never be positive, a `grant` can never be negative); both
  FKs off `CreditLedgerEntry` are `PROTECT`, so hard-deleting an
  organisation or a job can no longer silently erase or orphan the
  append-only record (`keel/billing/tests/test_constraints.py`).
  `credits.adjust` was updated to match: a clawback can no longer take
  the balance below zero (it raises `PaymentRequired` instead of hitting
  the constraint as a bare `IntegrityError`).
- **Reconciliation reports, never repairs, on a schedule** — `manage.py
rebuild_credit_balances --check` (and the nightly
  `check_credit_balances_task` beat task that wraps it) compares the
  ledger against the summary row and reports drift via Sentry without
  writing anything. Repair stays `rebuild_credit_balances` with no
  `--check` flag, run by an operator on purpose.
- **Webhook writes respect Stripe's actual delivery guarantees** —
  neither ordered nor at-most-once. `Subscription.stripe_updated_at`
  is an LWW version guard: a write only applies when its event is newer
  than the one that wrote the row last, so a late-delivered
  `customer.subscription.updated` can't resurrect a subscription a
  newer `customer.subscription.deleted` already cancelled.
  `invoice.paid` now only transitions `past_due` → `active`, never
  clobbers `canceled`/`trialing`/`incomplete` the way an unconditional
  update used to (`keel/billing/tests/test_webhooks_ordering.py`).
- **`StripeEvent.payload` doesn't grow forever** — a weekly beat task
  nulls the payload (keeping the id/type/timestamps that make it a
  usable dedup key) on processed events past a 30-day retention window.
  Unprocessed rows are never touched — they may still need replaying.
- **`/api/v1/plans/` and `/api/v1/permissions/` are cacheable** — both
  are Reference Data Holders (unauthenticated-safe, long-lived,
  read on every pricing-page/`/me/` load); both now carry
  `Cache-Control: public, max-age=300` and an `ETag`.
- **`Plan.entitlements` and the per-organisation entitlements blob on
  `/me/` are typed**, not `dict[str, Any]` — `EntitlementsOut` in
  `keel/billing/schemas.py`, reused by `organizations/schemas.py`'s
  `MeOrganizationOut` — so the generated TypeScript client can
  type-check a feature gate instead of casting an opaque map.

## What was deliberately left as-is

- **`daily_credit_cap` lives at the top level of `Plan.entitlements`,
  sibling to `features`/`limits`, not nested under either.** It's a
  different kind of thing (a rate over time, not a feature flag or a
  point-in-time count) and `credits._daily_cap` reads it directly. Kept
  separate rather than folded into `limits` so a plan with credits
  disabled can omit it entirely — `EntitlementsSpec` treats it as
  optional for exactly that reason.
- **`CreditLedgerEntry.actor` stays `SET_NULL`, not `PROTECT`.** A user
  can be deleted (account closure, GDPR) without that being blocked by
  every ledger row they ever acted on — unlike `organization`/`job`,
  losing the actor reference doesn't corrupt the append-only record's
  meaning, it just anonymises who performed a historical write.
