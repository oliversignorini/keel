/**
 * Hand-written types for the billing API surface (PRD §7; phase-4.md
 * Worktree C), for exactly the same reason lib/org/types.ts exists — see
 * that file's docstring.
 *
 * `CheckoutSessionView`, `BillingPortalView`, `SubscriptionView` and
 * `CreditBalanceView` (apps/api/keel/billing/views.py) are plain
 * `APIView`s with no `serializer_class`, so drf-spectacular emits no
 * response schema and orval generates `data: void` for all four —
 * verified in packages/api-client/src/generated/identity.query.ts after
 * regenerating against the post-billing-merge spec.
 *
 * `GET /api/v1/plans/` *is* typed by orval (PlanViewSet has a real
 * `serializer_class`), but only down to `prices: {[key: string]:
 * unknown}[]` — `PlanSerializer.get_prices` is a `SerializerMethodField`,
 * which drf-spectacular cannot see inside. Only the price shape is
 * restated below; the rest of `Plan` comes from the generated type.
 *
 * Every shape here is transcribed from apps/api/keel/billing/serializers.py
 * rather than guessed. Delete one the moment the matching view grows a
 * real `serializer_class` and `pnpm generate` produces it directly.
 */

import type { Plan } from "@keel/api-client";

/** `PriceSerializer` — one row of `PlanSerializer.get_prices`. */
export interface PlanPrice {
  id: string;
  interval: BillingInterval;
  /** Minor units (cents), as Stripe stores them. */
  unit_amount: number;
  currency: string;
}

/** `Price.INTERVAL_MONTH` / `Price.INTERVAL_YEAR` (billing/models.py). */
export type BillingInterval = "month" | "year";

/** `GET /api/v1/plans/` with `prices` narrowed past the
 * SerializerMethodField, and `entitlements` past the JSONField. */
export interface PlanWithPrices extends Omit<Plan, "prices" | "entitlements"> {
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

/** `SubscriptionSerializer`. `plan` is the plan *code* (the serializer
 * declares `source="plan.code"`), not an id. */
export interface Subscription {
  id: string;
  plan: string;
  status: SubscriptionStatus;
  quantity: number;
  current_period_end: string | null;
  trial_end: string | null;
  cancel_at_period_end: boolean;
}

/** Stripe's subscription statuses, passed through verbatim by the webhook
 * handlers (billing/webhooks.py). Only `trialing` and `past_due` are
 * given meaning by this app's UI — the trial and dunning banners. */
export type SubscriptionStatus =
  | "trialing"
  | "active"
  | "past_due"
  | "canceled"
  | "incomplete"
  | "incomplete_expired"
  | "unpaid"
  | "paused";

/** `GET /organizations/{slug}/billing/subscription/` — `null` when the
 * organisation has never checked out. */
export interface SubscriptionResponse {
  subscription: Subscription | null;
}

/** `POST /organizations/{slug}/billing/checkout/` and `.../portal/` both
 * return a Stripe-hosted URL to redirect to. */
export interface StripeRedirectResponse {
  url: string;
}

/** `POST /organizations/{slug}/billing/checkout/` body. */
export interface CheckoutBody {
  price_id: string;
}

/** `GET /organizations/{slug}/billing/credits/` — 404 (not zero) when
 * `BILLING_CREDITS` is off (billing/views.py `CreditBalanceView`). */
export interface CreditBalanceResponse {
  balance: number;
}

/** The per-organisation entitlement blob on `GET /api/v1/me/`, resolved
 * by `billing.entitlements.resolve_entitlements`. `lib/org/types.ts`
 * types it as the opaque `Record<string, unknown>` that view's missing
 * schema forces; this is the actual shape, and lib/billing/entitlements.ts
 * is the only thing that reads it. */
export interface ResolvedEntitlements {
  features: string[];
  limits: Record<string, number | null>;
}
