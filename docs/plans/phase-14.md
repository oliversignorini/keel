# Phase 14 — Billing and credits polish

**Source of truth:** Notion "Keel Phase 14", `keel-prd.md` §4 "Credits — the metered-billing primitive" and "Billing flow".
**Depends on:** Phase 10 merged.
**Size:** Small–Medium.
**Parallel with:** Phases 13 and 15.

---

## What already exists

`keel/billing/` is the most complete app in the repo: `credits.py`,
`entitlements.py`, `stripe_client.py`, `webhooks.py`, `tasks.py`, a
`CreditLedgerEntry` / `CreditBalance` pair, plans, checkout, portal, and a
100% coverage floor on the ledger arithmetic.

This is a **polish and audit** phase, not a build phase. The question it
answers is: *is this machinery generic, or has product-shaped thinking crept
in?*

## Boundary

**In scope:** `keel/billing/`, its tests, and billing documentation.

**Out of scope:**

| Thing | Owner |
|---|---|
| New billing features, new Stripe surface, tax, invoicing, dunning | Out of scope for a template — record as extension points |
| `keel/files`, `keel/jobs`, `keel/audit` | Phases 13 and 15, concurrent |
| The billing UI beyond what a change here forces | Minimal |

**No migrations** unless the audit finds a genuine modelling error, in which
case stop and report before writing one.

## Work

- **Audit for product-specific assumptions.** Read every model, service and
  setting asking: would a different product have to fight this? Named plan
  tiers, hard-coded credit costs, assumptions about what a credit buys,
  organisation-vs-user ownership ambiguity. Write down what you find before
  changing anything.
- **Confirm the ownership model** is unambiguous and documented: credits
  belong to the organisation, not the user — verify that is actually true
  everywhere, including impersonation paths.
- **Edge cases the ledger must survive**, each tested: concurrent
  consumption racing to zero, refund after balance changed, expiry mid-spend,
  a webhook replayed (Stripe retries — idempotency must hold), a webhook
  arriving out of order, consumption by a user whose membership was revoked
  mid-request.
- **`docs/billing.md`** — how a product plugs in. How to define what a
  credit means, how to add a plan, how to meter an operation, how to gate a
  feature on an entitlement. Concrete, with code, because this is the part a
  Keel consumer actually has to do.
- Confirm `BILLING_CREDITS` genuinely disables the whole credits surface —
  endpoints absent, not merely hidden. Test with the flag both ways, as
  `test_mfa` already does for MFA.

## Acceptance — evidence required

- [ ] The product-specific-assumption audit is written down, with what changed and what deliberately did not
- [ ] Every listed edge case has a test; the concurrency one uses real concurrent transactions, not a simulation
- [ ] Webhook replay and out-of-order delivery are provably idempotent
- [ ] Credits are organisation-owned everywhere, including under impersonation
- [ ] `BILLING_CREDITS=false` removes the endpoints, tested
- [ ] 100% coverage floor on `credits.py` still met
- [ ] `docs/billing.md` written with working examples
- [ ] No Brein-specific or product-specific concept anywhere in the diff

## Report back

What was already generic; what was not; anything you decided to leave
product-shaped and why.
