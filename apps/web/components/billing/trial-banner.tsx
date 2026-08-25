"use client";

import { formatDate } from "@/lib/billing/format";
import type { Subscription } from "@/lib/billing/types";

/**
 * Trial banner (phase-4.md Worktree C). `status === "trialing"` is the
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

  return (
    <div
      role="status"
      className="rounded-lg border border-blue-300 bg-blue-50 px-4 py-3 text-sm text-blue-900 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-200"
    >
      Your trial {ends}. Add a payment method before it ends to keep your plan.
    </div>
  );
}
