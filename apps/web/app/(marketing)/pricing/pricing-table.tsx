"use client";

import Link from "next/link";
import { useState } from "react";

import { featureLabel } from "@/lib/billing/feature-labels";
import { formatPrice } from "@/lib/billing/format";
import type { BillingInterval, PlanWithPrices } from "@/lib/billing/types";

const INTERVALS: { value: BillingInterval; label: string }[] = [
  { value: "month", label: "Monthly" },
  { value: "year", label: "Annual" },
];

/**
 * The monthly/annual toggle (phase-4.md Worktree C). The only interactive
 * part of the pricing page, and therefore the only client component on it
 * — the plan data itself is rendered on the server (see ./page.tsx) and
 * arrives as a prop, so switching interval is local state, not a refetch.
 *
 * A plan with no price at the selected interval is *hidden* for that
 * interval rather than shown priced at the other one: Stripe is the
 * source of truth for what is purchasable (phase-4.md B.1), and showing a
 * monthly price under an "Annual" heading would misstate what checkout
 * would actually charge.
 */
export function PricingTable({ plans }: { plans: PlanWithPrices[] }) {
  const [interval, setInterval] = useState<BillingInterval>("month");

  const priced = plans
    .map((plan) => ({ plan, price: plan.prices.find((row) => row.interval === interval) }))
    .filter((entry): entry is { plan: PlanWithPrices; price: NonNullable<typeof entry.price> } =>
      Boolean(entry.price),
    );

  return (
    <div className="mt-8">
      <div
        role="group"
        aria-label="Billing interval"
        className="inline-flex rounded-md border border-neutral-300 p-1 dark:border-neutral-700"
      >
        {INTERVALS.map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={interval === option.value}
            onClick={() => setInterval(option.value)}
            className={
              interval === option.value
                ? "rounded px-3 py-1 text-sm font-medium bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "rounded px-3 py-1 text-sm font-medium text-neutral-600 dark:text-neutral-400"
            }
          >
            {option.label}
          </button>
        ))}
      </div>

      {priced.length === 0 ? (
        <p className="mt-8 text-sm text-neutral-600 dark:text-neutral-400">
          No plans are available on this billing interval.
        </p>
      ) : (
        <ul className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {priced.map(({ plan, price }) => (
            <li
              key={plan.id}
              className="flex flex-col rounded-lg border border-neutral-200 p-6 dark:border-neutral-800"
            >
              <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
                {plan.name}
              </h2>
              <p className="mt-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
                {formatPrice(price.unit_amount, price.currency)}
                <span className="text-sm font-normal text-neutral-500 dark:text-neutral-400">
                  {interval === "month" ? " / month" : " / year"}
                </span>
              </p>
              <ul className="mt-4 flex flex-1 flex-col gap-1 text-sm text-neutral-600 dark:text-neutral-400">
                {(plan.entitlements?.features ?? []).map((feature) => (
                  <li key={feature}>{featureLabel(feature)}</li>
                ))}
              </ul>
              <Link
                href="/signup"
                className="mt-6 rounded-md bg-neutral-900 px-4 py-2 text-center text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
              >
                Start free trial
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
