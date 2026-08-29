"use client";

import Link from "next/link";
import { useState } from "react";
import { CheckIcon } from "lucide-react";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  buttonVariants,
} from "@keel/ui";

import { featureLabel } from "@/lib/billing/feature-labels";
import { formatPrice } from "@/lib/billing/format";
import type { BillingInterval, PlanWithPrices } from "@/lib/billing/types";

const INTERVALS: { value: BillingInterval; label: string }[] = [
  { value: "month", label: "Monthly" },
  { value: "year", label: "Annual" },
];

/**
 * The monthly/annual toggle. The only interactive
 * part of the pricing page, and therefore the only client component on it
 * — the plan data itself is rendered on the server (see ./page.tsx) and
 * arrives as a prop, so switching interval is local state, not a refetch.
 *
 * The toggle is a `<Tabs>` used as a segmented control, with one panel per
 * interval. The panels matter: a bare `TabsList` would leave every trigger
 * pointing `aria-controls` at an element that does not exist.
 *
 * A plan with no price at the selected interval is *hidden* for that
 * interval rather than shown priced at the other one: Stripe is the
 * source of truth for what is purchasable, and showing a
 * monthly price under an "Annual" heading would misstate what checkout
 * would actually charge.
 */
export function PricingTable({ plans }: { plans: PlanWithPrices[] }) {
  const [interval, setInterval] = useState<BillingInterval>("month");

  return (
    <Tabs
      value={interval}
      onValueChange={(value) => setInterval(value as BillingInterval)}
      className="mt-8 gap-0"
    >
      <TabsList aria-label="Billing interval">
        {INTERVALS.map((option) => (
          <TabsTrigger key={option.value} value={option.value}>
            {option.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {INTERVALS.map((option) => (
        <TabsContent key={option.value} value={option.value}>
          <PlanGrid plans={plans} interval={option.value} />
        </TabsContent>
      ))}
    </Tabs>
  );
}

function PlanGrid({ plans, interval }: { plans: PlanWithPrices[]; interval: BillingInterval }) {
  const priced = plans
    .map((plan) => ({ plan, price: plan.prices.find((row) => row.interval === interval) }))
    .filter((entry): entry is { plan: PlanWithPrices; price: NonNullable<typeof entry.price> } =>
      Boolean(entry.price),
    );

  if (priced.length === 0) {
    return (
      <p className="mt-8 text-sm text-muted-foreground">
        No plans are available on this billing interval.
      </p>
    );
  }

  return (
    <ul className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
      {priced.map(({ plan, price }) => (
        <li key={plan.id} className="flex">
          <Card className="flex-1">
            <CardHeader>
              <CardTitle className="text-lg">{plan.name}</CardTitle>
              <p className="text-2xl font-semibold text-foreground">
                {formatPrice(price.unit_amount, price.currency)}
                <span className="text-sm font-normal text-muted-foreground">
                  {interval === "month" ? " / month" : " / year"}
                </span>
              </p>
            </CardHeader>
            <CardContent className="flex-1">
              <ul className="flex flex-col gap-2 text-sm text-muted-foreground">
                {(plan.entitlements?.features ?? []).map((feature) => (
                  <li key={feature} className="flex items-start gap-2">
                    <CheckIcon className="mt-0.5 size-4 shrink-0 text-foreground" aria-hidden />
                    {featureLabel(feature)}
                  </li>
                ))}
              </ul>
            </CardContent>
            <CardFooter>
              <Link href="/signup" className={buttonVariants({ className: "w-full" })}>
                Start free trial
              </Link>
            </CardFooter>
          </Card>
        </li>
      ))}
    </ul>
  );
}
