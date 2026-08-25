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
  organizationsBillingCheckoutCreate,
  organizationsBillingCreditsRetrieve,
  organizationsBillingPortalCreate,
  organizationsBillingSubscriptionRetrieve,
  plansList,
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
  const result = await plansList();
  return result.data as unknown as PlanWithPrices[];
}

export async function getSubscription(orgSlug: string): Promise<SubscriptionResponse> {
  const result = await organizationsBillingSubscriptionRetrieve(orgSlug);
  return result.data as unknown as SubscriptionResponse;
}

/** Requires `billing.manage`. The returned URL is Stripe's Customer
 * Portal, which is also where invoice history lives — there is no
 * separate invoice endpoint in this API (phase-4.md Worktree C's "invoice
 * access"). */
export async function createPortalSession(orgSlug: string): Promise<StripeRedirectResponse> {
  const result = await organizationsBillingPortalCreate(orgSlug, { method: "POST" });
  return result.data as unknown as StripeRedirectResponse;
}

/** Requires `billing.manage`. */
export async function createCheckoutSession(
  orgSlug: string,
  body: CheckoutBody,
): Promise<StripeRedirectResponse> {
  const result = await organizationsBillingCheckoutCreate(orgSlug, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return result.data as unknown as StripeRedirectResponse;
}

/** Requires `billing.view`. Throws `NotFoundError` when `BILLING_CREDITS`
 * is off server-side — the flag decides whether this endpoint exists at
 * all (billing/views.py `CreditBalanceView`). */
export async function getCreditBalance(orgSlug: string): Promise<CreditBalanceResponse> {
  const result = await organizationsBillingCreditsRetrieve(orgSlug);
  return result.data as unknown as CreditBalanceResponse;
}
