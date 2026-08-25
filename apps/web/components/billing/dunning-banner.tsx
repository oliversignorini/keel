"use client";

import Link from "next/link";

import { Can } from "@/components/org/can";
import type { Subscription } from "@/lib/billing/types";
import { Perm } from "@/lib/org/permissions";

/**
 * Dunning banner (phase-4.md B.6, and the acceptance box "`payment_failed`
 * puts the org into a dunning state; the banner appears; access is not
 * immediately revoked").
 *
 * `status === "past_due"` is the dunning state — set by
 * billing/webhooks.py's `_handle_invoice_payment_failed` and cleared on
 * `invoice.paid`. The copy deliberately does not threaten immediate
 * suspension, because nothing is suspended: this banner is the *whole* of
 * what dunning does to the product, and the fix link is only shown to
 * someone who can actually act on it (`billing.manage`).
 */
export function DunningBanner({
  subscription,
  orgSlug,
}: {
  subscription: Subscription | null;
  orgSlug: string;
}) {
  if (!subscription || subscription.status !== "past_due") return null;

  return (
    <div
      role="alert"
      className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
    >
      We couldn&apos;t take payment for your last invoice. Your organisation keeps working — update
      your payment details to avoid interruption.{" "}
      <Can code={Perm.BILLING_MANAGE}>
        <Link href={`/${orgSlug}/settings/billing`} className="font-medium underline">
          Update payment details
        </Link>
      </Can>
    </div>
  );
}
