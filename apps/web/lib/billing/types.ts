/**
 * Hand-written types for the billing API surface (PRD §7; phase-4.md
 * Worktree C).
 *
 * Phase 10 (DRF -> Django Ninja) gave the checkout, portal, subscription
 * and credit-balance routes real generated schemas (`CheckoutSessionOut`,
 * `BillingPortalOut`, `SubscriptionEnvelopeOut`, `CreditBalanceOut` —
 * `apps/api/keel/billing/schemas.py`), so the shapes those routes used to
 * need hand-transcribed here are now aliases onto the generated type.
 *
 * `GET /api/v1/plans/` still needs `PlanPrice`/`PlanEntitlements` below:
 * `PlanOut.prices`/`entitlements` are typed by the generated schema, but
 * only down to `Record<string, unknown>` — `Plan.entitlements` is a
 * Postgres JSONField with no schema of its own (api-patterns finding 15;
 * a real `EntitlementsOut` schema is fold-into-phase-14, not this pass).
 */

import type {
  CheckoutIn,
  CheckoutSessionOut,
  CreditBalanceOut,
  PlanOut,
  SubscriptionEnvelopeOut,
  SubscriptionOut,
  SubscriptionOutStatus,
} from "@keel/api-client";

/** `PriceOut` — one row of `PlanOut.prices`. */
export interface PlanPrice {
  id: string;
  interval: BillingInterval;
  /** Minor units (cents), as Stripe stores them. */
  unit_amount: number;
  currency: string;
}

/** `Price.INTERVAL_MONTH` / `Price.INTERVAL_YEAR` (billing/models.py). */
export type BillingInterval = "month" | "year";

/** `GET /api/v1/plans/` with `prices` narrowed past the generated
 * `Record<string, unknown>`, and `entitlements` past the JSONField. */
export interface PlanWithPrices extends Omit<PlanOut, "prices" | "entitlements"> {
  prices: PlanPrice[];
  entitlements: PlanEntitlements;
}

/** `Plan.entitlements`' shape, per billing/entitlements.py's docstring: a
 * feature list and a per-resource limit map, where a missing key or an
 * explicit `null` means "not capped by this plan". */
export interface PlanEntitlements {
  features?: string[];
  limits?: Record<string, number | null>;
  [key: string]: unknown;
}

/** `plan` is the plan *code* (`SubscriptionOut.resolve_plan`), not an id. */
export type Subscription = SubscriptionOut;

/** Stripe's own subscription-status vocabulary (billing/schemas.py's
 * `SubscriptionStatus` — Stripe, not this table, is the source of truth).
 * Only `trialing` and `past_due` are given meaning by this app's UI — the
 * trial and dunning banners. */
export type SubscriptionStatus = SubscriptionOutStatus;

/** `GET /orgs/{slug}/billing/subscription/` — `null` when the
 * organisation has never checked out. */
export type SubscriptionResponse = SubscriptionEnvelopeOut;

/** `POST /orgs/{slug}/billing/checkout/` and `.../portal/` both return a
 * Stripe-hosted URL to redirect to (`CheckoutSessionOut`/
 * `BillingPortalOut` are identical one-field shapes). */
export type StripeRedirectResponse = CheckoutSessionOut;

/** `POST /orgs/{slug}/billing/checkout/` body. */
export type CheckoutBody = CheckoutIn;

/** `GET /orgs/{slug}/billing/credits/` — 404 (not zero) when
 * `BILLING_CREDITS` is off (billing/views.py `get_credit_balance`). */
export type CreditBalanceResponse = CreditBalanceOut;

/** The per-organisation entitlement blob on `GET /api/v1/me/`, resolved
 * by `billing.entitlements.resolve_entitlements`. `lib/org/types.ts`
 * types it as the opaque `Record<string, unknown>` that view's missing
 * schema forces; this is the actual shape, and lib/billing/entitlements.ts
 * is the only thing that reads it. */
export interface ResolvedEntitlements {
  features: string[];
  limits: Record<string, number | null>;
}
