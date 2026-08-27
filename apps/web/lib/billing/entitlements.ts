/**
 * Reading entitlements on the client (phase-4.md Worktree C: "The client
 * renders from the permission and entitlement lists in `/me`. It is never
 * the enforcement point.").
 *
 * Everything here decides what to *show*. The API decides what is
 * allowed: `billing/entitlements.py`'s `check_feature` / `check_limit`
 * raise 402 regardless of what this file concluded, which is what
 * components/billing/entitlement-gate.presentation-only.test.tsx proves
 * by skipping the gate entirely.
 */

import type { MeOrganization } from "@/lib/org/types";

import type { PlanPrice, PlanWithPrices, ResolvedEntitlements } from "./types";

const EMPTY: Required<ResolvedEntitlements> = { features: [], limits: {} };

/**
 * `/api/v1/me/`'s per-organisation `entitlements` blob, narrowed. An
 * organisation with no subscription resolves server-side to `{"features":
 * [], "limits": {}}` (billing/entitlements.py `resolve_entitlements`), so
 * a missing or malformed blob is treated as exactly that rather than as
 * an error — an unsubscribed org is a normal state, not a fault.
 *
 * `EntitlementsOut`'s own fields are optional (a plan may omit either),
 * so this always fills both in — the return type is `Required<...>`,
 * not the bare generated shape, precisely so callers never have to
 * re-check for `undefined`.
 */
export function readEntitlements(org: MeOrganization | null): Required<ResolvedEntitlements> {
  const raw = org?.entitlements;
  if (!raw) return EMPTY;
  return {
    features: Array.isArray(raw.features) ? raw.features : [],
    limits: raw.limits && typeof raw.limits === "object" ? raw.limits : {},
  };
}

export function hasFeature(org: MeOrganization | null, feature: string): boolean {
  return readEntitlements(org).features.includes(feature);
}

/**
 * The cheapest plan in the catalogue that includes `feature` — what an
 * upgrade prompt names, since phase-4.md asks the gate to name "the
 * required plan instead of the feature". Cheapest is by lowest monthly
 * price (falling back to a plan's lowest price of any interval), with
 * `sort_order` breaking ties, so the answer is the *entry* plan that
 * unlocks the feature rather than whichever plan happens to sort first.
 *
 * `null` when no plan grants the feature — the caller then shows a
 * generic prompt rather than inventing a plan name.
 */
export function cheapestPlanWithFeature(
  plans: PlanWithPrices[],
  feature: string,
): PlanWithPrices | null {
  const candidates = plans.filter((plan) => (plan.entitlements?.features ?? []).includes(feature));
  if (candidates.length === 0) return null;
  return candidates.reduce((cheapest, plan) => {
    const byPrice = comparablePrice(plan) - comparablePrice(cheapest);
    const ranking = byPrice !== 0 ? byPrice : (plan.sort_order ?? 0) - (cheapest.sort_order ?? 0);
    return ranking < 0 ? plan : cheapest;
  });
}

function comparablePrice(plan: PlanWithPrices): number {
  const monthly = plan.prices.find((price: PlanPrice) => price.interval === "month");
  if (monthly) return monthly.unit_amount;
  const amounts = plan.prices.map((price: PlanPrice) => price.unit_amount);
  return amounts.length > 0 ? Math.min(...amounts) : Number.POSITIVE_INFINITY;
}
