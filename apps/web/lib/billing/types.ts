/**
 * Hand-written types for the billing API surface.
 *
 * The DRF -> Django Ninja migration gave the checkout, portal, subscription
 * and credit-balance routes real generated schemas (`CheckoutSessionOut`,
 * `BillingPortalOut`, `SubscriptionEnvelopeOut`, `CreditBalanceOut` —
 * `apps/api/keel/billing/schemas.py`), so the shapes those routes used to
 * need hand-transcribed here are now aliases onto the generated type.
 *
 * The same was done for `Plan.entitlements`: it's a real
 * `EntitlementsOut` schema now, not a `Record<string,
 * unknown>` JSONField blob — `PlanEntitlements`/`ResolvedEntitlements`
 * below are aliases onto the generated type, kept only so call sites
 * don't have to import `EntitlementsOut` under two different names for
 * the plan-catalogue and `/me/` cases.
 */

import type {
  CheckoutIn,
  CheckoutSessionOut,
  CreditBalanceOut,
  EntitlementsOut,
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
 * `Record<string, unknown>`. */
export interface PlanWithPrices extends Omit<PlanOut, "prices"> {
  prices: PlanPrice[];
}

/** `Plan.entitlements`' shape, per billing/entitlements.py's docstring: a
 * feature list and a per-resource limit map, where a missing key or an
 * explicit `null` means "not capped by this plan". */
export type PlanEntitlements = EntitlementsOut;

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
 * by `billing.entitlements.resolve_entitlements` and typed by the same
 * generated `EntitlementsOut` schema `PlanEntitlements` above aliases —
 * `lib/billing/entitlements.ts` is the only thing that reads it. */
export type ResolvedEntitlements = EntitlementsOut;
