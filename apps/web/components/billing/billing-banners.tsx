"use client";

import { DunningBanner } from "./dunning-banner";
import { TrialBanner } from "./trial-banner";
import { useSubscription } from "@/lib/billing/use-subscription";

/**
 * Both billing banners, mounted once per organisation at the
 * `/app/[org]` layout level rather than on the billing settings page.
 *
 * That placement is the point of them. "The banner appears" (phase-4.md
 * B.6 / the dunning acceptance box) has to mean *while you are using the
 * product* — a dunning notice only visible on the settings page you have
 * no reason to open is a notice nobody sees, and dunning is precisely the
 * state where the product keeps working and the user has no other signal
 * that anything is wrong. Same for a trial about to end.
 *
 * The cost is one extra `GET .../billing/subscription/` per organisation
 * page load, which is the same request the billing settings page makes
 * anyway. A role without `billing.view` gets a 403 and sees nothing (see
 * useSubscription's `unavailable`).
 */
export function BillingBanners({ orgSlug }: { orgSlug: string }) {
  const { subscription, loading, unavailable } = useSubscription(orgSlug);

  if (loading || unavailable || !subscription) return null;
  // Neither banner has anything to say in any other status, and an empty
  // spacer div at the top of every page would be visible even so.
  if (subscription.status !== "trialing" && subscription.status !== "past_due") return null;

  return (
    <div className="mb-6 flex flex-col gap-3">
      <TrialBanner subscription={subscription} />
      <DunningBanner subscription={subscription} orgSlug={orgSlug} />
    </div>
  );
}
