/**
 * Thin, typed wrappers around the generated billing client — the same
 * shape, and for the same reasons, as lib/org/api.ts (see its docstring).
 * Nothing here reimplements transport, auth, or error handling;
 * `identityFetch` (packages/api-client/src/http/mutator.ts) already does
 * all three, including turning a 402 into a `PaymentRequiredError` and a
 * 404 into a `NotFoundError`, which is what `<EntitlementGate>` and
 * `<CreditMeter>` narrow on.
 */

import {
  unwrapData,
  createBillingPortalSession,
  createCheckoutSession as generatedCreateCheckoutSession,
  retrieveCreditBalance as generatedRetrieveCreditBalance,
  retrieveSubscription as generatedRetrieveSubscription,
  listPlans as listPlansGenerated,
} from "@keel/api-client";

import type {
  CheckoutBody,
  CreditBalanceResponse,
  PlanWithPrices,
  StripeRedirectResponse,
  SubscriptionResponse,
} from "./types";

/** `GET /api/v1/plans/` — public (AllowAny) and unpaginated, so this is
 * safe to call from a server component with no session (see
 * app/pricing/page.tsx). */
export async function listPlans(): Promise<PlanWithPrices[]> {
  const result = await listPlansGenerated();
  return unwrapData(result).results as unknown as PlanWithPrices[];
}

export async function getSubscription(orgSlug: string): Promise<SubscriptionResponse> {
  const result = await generatedRetrieveSubscription(orgSlug);
  return unwrapData(result);
}

/** Requires `billing.manage`. The returned URL is Stripe's Customer
 * Portal, which is also where invoice history lives — there is no
 * separate invoice endpoint in this API. */
export async function createPortalSession(orgSlug: string): Promise<StripeRedirectResponse> {
  const result = await createBillingPortalSession(orgSlug, { method: "POST" });
  return unwrapData(result);
}

/** Requires `billing.manage`. */
export async function createCheckoutSession(
  orgSlug: string,
  body: CheckoutBody,
): Promise<StripeRedirectResponse> {
  const result = await generatedCreateCheckoutSession(orgSlug, body);
  return unwrapData(result);
}

/** Requires `billing.view`. Throws `NotFoundError` when `BILLING_CREDITS`
 * is off server-side — the flag decides whether this endpoint exists at
 * all (billing/views.py `get_credit_balance`). */
export async function getCreditBalance(orgSlug: string): Promise<CreditBalanceResponse> {
  const result = await generatedRetrieveCreditBalance(orgSlug);
  return unwrapData(result);
}
