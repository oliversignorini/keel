# Phase 4 — Billing

**Source of truth:** `keel-prd.md` v1.2 — §4 "Data model", "Credits — the metered-billing primitive", "Billing flow", §6 "Stripe webhook", §7 billing and credits endpoints, §8 Phase 4.
**Depends on:** Phase 3 merged (permission codes, `has_perm`, organisation resolution).
**Size:** Large. Three worktrees; two of them start together.

---

## Three worktrees

| Worktree | Owns | Starts |
|---|---|---|
| **`p4-credits`** | `billing/credits.py`, the ledger, the balance row, the double-spend test | With `p4-billing-api` — it touches no Stripe code |
| **`p4-billing-api`** | Plans, prices, subscriptions, checkout, portal, webhooks, entitlements, seat sync | With `p4-credits` |
| **`p4-billing-web`** | Pricing page, billing settings, `<EntitlementGate>`, `<CreditMeter>`, trial and dunning banners | After both API worktrees merge |

`p4-credits` and `p4-billing-api` are genuinely independent: the ledger is arithmetic over local rows and never calls Stripe, and the Stripe surface never reads a ledger balance. They meet only at `Plan.entitlements`, which is data.

**No worktree writes migrations.** Every table exists from Phase 1: `Plan`, `Price`, `Subscription`, `StripeEvent`, `CreditLedgerEntry`, `CreditBalance`. A needed migration is a Phase 1 gap — report it.

**No credentials.** `stripe-mock` or recorded fixtures throughout. Real keys are a later wiring task and are not a blocker for any acceptance criterion below. Where a criterion genuinely cannot be met without a live account — Stripe test clocks are the likely case — say so explicitly rather than faking a pass.

---

# Worktree A — `p4-credits`

Gated at **100% coverage** on `billing/credits.py` (PRD invariant 7). That is achievable because the module is pure arithmetic over rows; if it is hard to reach, the module is doing too much.

### A.1 — The arithmetic

`billing/credits.py`: `estimate`, `hold`, `consume`, `release`, `refund`, and the balance read.

The ledger is the truth; `CreditBalance` is an index. Every entry is append-only — never updated, never deleted. A correction is an `adjustment` row with a reason and an actor, not an `UPDATE`.

### A.2 — Concurrency, which is the whole point

`CreditBalance` is written in the same transaction as the entry, with `SELECT … FOR UPDATE` on that row serialising concurrent holds.

The named acceptance criterion is: **three concurrent holds against a balance sufficient for two produce exactly two holds and one 402.** Run it against a real Postgres with real threads or processes — not with mocked locking, which tests nothing. This test is the reason the ledger exists instead of an integer column, and a version of it that passes without genuine concurrency is worse than no test.

### A.3 — Lifecycle

- A job finishing under estimate `release`s the remainder.
- A failed job's hold is fully `refund`ed.
- Balance equals `SUM(amount)` after every case.
- A management command rebuilds `CreditBalance` from the ledger and reproduces the same number.
- A per-organisation daily spend cap as a query over the ledger — not a new mechanism, not a new column. Exceeding it returns 402 with the cap in `details`.

### A.4 — Admin

Operator adjustment in Django admin requires a reason, records the actor, and writes an audit row via Phase 1's `@audited`.

### A.5 — Flag

Everything ships behind `BILLING_CREDITS`, **off by default**. With it off: no endpoints, no meter, no cost. The models exist regardless — that is what makes enabling it a settings change rather than a migration. Test both states.

---

# Worktree B — `p4-billing-api`

### B.1 — Plans and prices

`sync_stripe_plans` management command. Stripe is the source of truth for pricing; local rows are a cache, refreshed nightly by beat (the beat entry is Phase 5's to schedule — write the task, note the dependency).

`GET /api/v1/plans/` is **public** — the pricing page reads it unauthenticated. It is therefore a `GlobalViewSet` and needs a `GLOBAL_JUSTIFICATION`. Write a real one.

### B.2 — Checkout and portal

- `POST /orgs/{slug}/billing/checkout/` → Checkout Session URL. `automatic_tax` enabled, AUD default, 14-day trial without card. Requires `billing.manage`.
- `POST /orgs/{slug}/billing/portal/` → Customer Portal URL. Requires `billing.manage`.
- `GET /orgs/{slug}/billing/subscription/` requires `billing.view`.

**No Stripe call happens inside an open transaction** (invariant 3). Mutate local state inside `transaction.atomic()`, dispatch the external call via `transaction.on_commit()`. This is a lint-able rule and a test-able one; do both.

### B.3 — Webhooks — the part that must be right

`POST /api/v1/stripe/webhook/`:

1. Verify the signature. Unsigned or wrongly-signed → 400, log, change nothing, no retry.
2. `StripeEvent.objects.get_or_create(id=event.id)`. Already processed → 200 immediately, an idempotent no-op.
3. Enqueue processing. **Acknowledge in under 200ms** — Stripe requires a fast ack and the work happens async.

Worker: atomic dispatch to the handler, upsert `Subscription`, retry with backoff ×5, then `StripeEvent.error` plus a Sentry event.

Handled events: `checkout.session.completed`, `customer.subscription.created|updated|deleted`, `invoice.paid`, `invoice.payment_failed`.

**Every handled event type is replayed twice in an explicit test module with no coverage exemption**, asserting identical state after the second delivery. Replay is not "call the handler twice in one transaction" — deliver the webhook twice the way Stripe would.

### B.4 — Entitlements

- `Plan.entitlements` JSON: seats, per-resource quantities, feature list.
- `@requires_entitlement("api_access")` gates features; `check_limit(org, "widgets")` gates quantities. Both in `billing/services.py`, both raising typed exceptions that map to 402 with upgrade context in `details`.
- Plan downgrade below current usage is blocked with a message that names what is over.
- Resolution feeds `GET /api/v1/me/`, which Phase 3 owns — coordinate rather than duplicating it.

### B.5 — Seat sync, behind `BILLING_SEAT_PRICING`, off by default

When on: seat count syncs to Stripe with proration on membership create and remove, dispatched from `organizations/services.py` via `transaction.on_commit()`, never inline.

When off: **no Stripe call is made, and membership writes succeed while Stripe is unreachable.** Test that explicitly — it is the reason the flag exists.

### B.6 — Dunning

`invoice.payment_failed` puts the organisation into a dunning state. The banner appears. **Access is not immediately revoked.**

---

# Worktree C — `p4-billing-web`

Starts after A and B merge.

- Pricing page reading live from `/api/v1/plans/`, monthly/annual toggle. Static where it can be, so PRD Phase 7's Lighthouse gate stays reachable.
- `/app/[org]/settings/billing` — current plan, subscription state, portal link, invoice access.
- `<EntitlementGate>` — renders an upgrade prompt naming the required plan instead of the feature, on 402.
- `<CreditMeter>` — balance, pre-flight estimate on the confirm dialog, 402 handling. Rendered **only when credits are enabled**.
- Trial banner and dunning banner.

The client renders from the permission and entitlement lists in `/me`. It is never the enforcement point. Removing a gate client-side must still yield 402 from the API — test that.

---

## Acceptance — evidence required

From PRD §8 Phase 4:

- [ ] Checkout completes and the subscription appears without manual intervention
- [ ] **Every handled webhook event replayed twice produces identical state**
- [ ] An unsigned or wrongly-signed webhook returns 400 and changes nothing
- [ ] Webhook endpoint acknowledges in under 200ms; processing is async
- [ ] Adding a member beyond the seat entitlement returns 402 with upgrade context
- [ ] With `BILLING_SEAT_PRICING` on, removing a member decrements the Stripe quantity with proration; with it off, no Stripe call is made and membership writes succeed while Stripe is unreachable
- [ ] **Three concurrent holds against a balance sufficient for two produce exactly two holds and one 402** — real database, real concurrency
- [ ] A failed job's hold is fully refunded; a job finishing under estimate releases the remainder; balance equals `SUM(amount)` after every case
- [ ] Rebuilding `CreditBalance` from the ledger reproduces the same number
- [ ] An operator adjustment in Django admin requires a reason and writes an audit row
- [ ] Plan downgrade below current usage is blocked with a clear message
- [ ] `payment_failed` puts the org into a dunning state; the banner appears; access is not immediately revoked
- [ ] Stripe test-clock scenarios cover trial end, renewal and cancellation — **or** it is stated plainly that this needs a live test account and is deferred, with the exact scenarios listed
- [ ] `billing/credits.py` is at 100% coverage
- [ ] No Stripe call occurs inside an open transaction
- [ ] No migrations were generated
- [ ] With both flags off, no credit or seat code path executes and no endpoint is exposed

---

## How to work

- Strict TDD on both API worktrees. Tests alongside on the web worktree.
- Verify, do not assert. Every box needs pasted output.
- Update the Orca worktree comment at each task boundary.
- Do not push, do not open a PR — the orchestrator merges.
- Every commit message body ends with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AQXQvAv8g92xotjrnnibLc
```

## Report back

Acceptance boxes with evidence; what the double-spend test actually did to achieve real concurrency; anything deferred for want of a live Stripe account, listed precisely; decisions the plan did not cover; anything in the PRD that looked wrong from inside the code.
