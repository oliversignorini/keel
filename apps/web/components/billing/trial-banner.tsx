"use client";

import { Alert, AlertDescription, AlertTitle } from "@keel/ui";
import { Clock } from "lucide-react";

import { formatDate } from "@/lib/billing/format";
import type { Subscription } from "@/lib/billing/types";

/**
 * Trial banner. `status === "trialing"` is the
 * only trigger: `trial_end` outlives the trial on the Stripe object, so a
 * banner keyed on the date alone would keep showing after the first
 * successful payment.
 *
 * Presentational — it takes the subscription rather than fetching one, so
 * the page that already loaded it (settings/billing) and the layout-level
 * `<BillingBanners>` share one request between them.
 */
export function TrialBanner({ subscription }: { subscription: Subscription | null }) {
  if (!subscription || subscription.status !== "trialing") return null;

  const ends = subscription.trial_end ? `ends ${formatDate(subscription.trial_end)}` : "is running";

  // `role="status"` rather than <Alert>'s default `role="alert"`: a trial
  // in progress is not an assertive interruption.
  return (
    <Alert role="status">
      <Clock />
      <AlertTitle>Your trial {ends}.</AlertTitle>
      <AlertDescription>Add a payment method before it ends to keep your plan.</AlertDescription>
    </Alert>
  );
}
