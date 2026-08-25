"use client";

import { useEffect, useState } from "react";

import { CreditMeter } from "@/components/billing/credit-meter";
import { DunningBanner } from "@/components/billing/dunning-banner";
import { TrialBanner } from "@/components/billing/trial-banner";
import { Can } from "@/components/org/can";
import { createCheckoutSession, createPortalSession, listPlans } from "@/lib/billing/api";
import { formatDate, formatPrice } from "@/lib/billing/format";
import type { PlanWithPrices, Subscription } from "@/lib/billing/types";
import { useSubscription } from "@/lib/billing/use-subscription";
import { useOrgContext } from "@/lib/org/org-context";
import { Perm } from "@/lib/org/permissions";

/**
 * `/app/[org]/settings/billing` (PRD §5 Routes; phase-4.md Worktree C:
 * "current plan, subscription state, portal link, invoice access").
 *
 * Invoice access is the portal link: `BillingPortalView` returns a Stripe
 * Customer Portal URL, and invoice history lives there — this API has no
 * invoice endpoint of its own, and adding one would mean re-hosting data
 * Stripe already renders (and bills for) correctly.
 *
 * Every action is wrapped in `<Can code="billing.manage">`, which is
 * presentation only (components/org/can.tsx): the same POST would still
 * hit `_OrganizationBillingView`'s permission check with the gate removed.
 */
export default function BillingSettingsPage() {
  const { currentOrg } = useOrgContext();
  const orgSlug = currentOrg?.slug ?? "";
  const { subscription, loading } = useSubscription(orgSlug);

  if (!currentOrg) return null;

  return (
    <div className="flex flex-col gap-8">
      <TrialBanner subscription={subscription} />
      <DunningBanner subscription={subscription} orgSlug={orgSlug} />

      <section>
        <h2 className="mb-4 text-lg font-semibold text-neutral-900 dark:text-neutral-100">Plan</h2>
        {loading ? (
          <p role="status" className="text-sm text-neutral-600 dark:text-neutral-400">
            Loading…
          </p>
        ) : subscription ? (
          <CurrentPlan subscription={subscription} />
        ) : (
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            This organisation isn&apos;t on a plan yet.
          </p>
        )}
      </section>

      <CreditMeter orgSlug={orgSlug} />

      <Can code={Perm.BILLING_MANAGE}>
        {subscription ? (
          <ManageBillingSection orgSlug={orgSlug} />
        ) : (
          <UpgradeSection orgSlug={orgSlug} />
        )}
      </Can>
    </div>
  );
}

function CurrentPlan({ subscription }: { subscription: Subscription }) {
  return (
    <dl className="grid max-w-md grid-cols-2 gap-y-2 text-sm">
      <dt className="text-neutral-500 dark:text-neutral-400">Plan</dt>
      <dd className="text-neutral-900 dark:text-neutral-100">{subscription.plan}</dd>
      <dt className="text-neutral-500 dark:text-neutral-400">Status</dt>
      <dd className="text-neutral-900 dark:text-neutral-100">{subscription.status}</dd>
      <dt className="text-neutral-500 dark:text-neutral-400">Seats</dt>
      <dd className="text-neutral-900 dark:text-neutral-100">{subscription.quantity}</dd>
      {subscription.current_period_end ? (
        <>
          <dt className="text-neutral-500 dark:text-neutral-400">
            {subscription.cancel_at_period_end ? "Ends" : "Renews"}
          </dt>
          <dd className="text-neutral-900 dark:text-neutral-100">
            {formatDate(subscription.current_period_end)}
          </dd>
        </>
      ) : null}
    </dl>
  );
}

/**
 * The portal is a redirect, not an embedded surface: the POST returns a
 * Stripe-hosted URL and the browser leaves for it (`BillingPortalView`
 * passes a `return_url` back to this page).
 */
function ManageBillingSection({ orgSlug }: { orgSlug: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function openPortal() {
    setBusy(true);
    setError(null);
    try {
      const { url } = await createPortalSession(orgSlug);
      window.location.assign(url);
    } catch {
      setError("Could not open the billing portal. Try again.");
      setBusy(false);
    }
  }

  return (
    <section>
      <h2 className="mb-1 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        Manage billing
      </h2>
      <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-400">
        Change plan, update your payment details, or download invoices.
      </p>
      {error ? <p className="mb-2 text-sm text-red-600 dark:text-red-400">{error}</p> : null}
      <button
        type="button"
        onClick={() => void openPortal()}
        disabled={busy}
        className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
      >
        {busy ? "Opening…" : "Manage billing"}
      </button>
    </section>
  );
}

/** No subscription yet: pick a plan and go to Checkout. */
function UpgradeSection({ orgSlug }: { orgSlug: string }) {
  const [plans, setPlans] = useState<PlanWithPrices[]>([]);
  const [busyPriceId, setBusyPriceId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listPlans()
      .then((result) => {
        if (!cancelled) setPlans(result);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load plans.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function checkout(priceId: string) {
    setBusyPriceId(priceId);
    setError(null);
    try {
      const { url } = await createCheckoutSession(orgSlug, { price_id: priceId });
      window.location.assign(url);
    } catch {
      setError("Could not start checkout. Try again.");
      setBusyPriceId(null);
    }
  }

  return (
    <section>
      <h2 className="mb-1 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        Choose a plan
      </h2>
      <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-400">
        Includes a 14-day trial. No card required to start.
      </p>
      {error ? <p className="mb-2 text-sm text-red-600 dark:text-red-400">{error}</p> : null}
      <ul className="flex flex-wrap gap-3">
        {plans.map((plan) => {
          const price = plan.prices.find((candidate) => candidate.interval === "month");
          if (!price) return null;
          return (
            <li key={plan.id}>
              <button
                type="button"
                onClick={() => void checkout(price.id)}
                disabled={busyPriceId !== null}
                className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium disabled:opacity-50 dark:border-neutral-700"
              >
                {busyPriceId === price.id
                  ? "Starting…"
                  : `${plan.name} — ${formatPrice(price.unit_amount, price.currency)}/month`}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
