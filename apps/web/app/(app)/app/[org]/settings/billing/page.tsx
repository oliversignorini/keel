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
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Skeleton,
} from "@keel/ui";
import { ExternalLink } from "lucide-react";

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
    <div className="flex flex-col gap-6">
      <TrialBanner subscription={subscription} />
      <DunningBanner subscription={subscription} orgSlug={orgSlug} />

      <Card>
        <CardHeader>
          <CardTitle>Plan</CardTitle>
          <CardDescription>What this organisation is currently subscribed to.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div role="status" aria-label="Loading plan" className="flex flex-col gap-3">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-5 w-32" />
              <Skeleton className="h-5 w-40" />
            </div>
          ) : subscription ? (
            <CurrentPlan subscription={subscription} />
          ) : (
            <p className="text-sm text-muted-foreground">
              This organisation isn&apos;t on a plan yet.
            </p>
          )}
        </CardContent>
      </Card>

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

/** `past_due` → `Past due`; Stripe's snake_case is not a label. */
function statusLabel(status: string): string {
  const words = status.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function statusVariant(status: string): "success" | "warning" | "destructive" | "secondary" {
  if (status === "active") return "success";
  if (status === "trialing") return "warning";
  if (status === "past_due" || status === "unpaid") return "destructive";
  return "secondary";
}

function CurrentPlan({ subscription }: { subscription: Subscription }) {
  return (
    <dl className="grid max-w-md grid-cols-2 gap-y-3 text-sm">
      <dt className="text-muted-foreground">Plan</dt>
      <dd className="text-foreground">{subscription.plan}</dd>
      <dt className="text-muted-foreground">Status</dt>
      <dd>
        <Badge variant={statusVariant(subscription.status)}>
          {statusLabel(subscription.status)}
        </Badge>
      </dd>
      <dt className="text-muted-foreground">Seats</dt>
      <dd className="text-foreground">{subscription.quantity}</dd>
      {subscription.current_period_end ? (
        <>
          <dt className="text-muted-foreground">
            {subscription.cancel_at_period_end ? "Ends" : "Renews"}
          </dt>
          <dd className="text-foreground">{formatDate(subscription.current_period_end)}</dd>
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
    <Card>
      <CardHeader>
        <CardTitle>Manage billing</CardTitle>
        <CardDescription>
          Change plan, update your payment details, or download invoices.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? <p className="mb-2 text-sm text-destructive">{error}</p> : null}
        <Button onClick={() => void openPortal()} disabled={busy}>
          {busy ? "Opening…" : "Manage billing"}
          <ExternalLink />
        </Button>
      </CardContent>
    </Card>
  );
}

/** No subscription yet: pick a plan and go to Checkout. */
function UpgradeSection({ orgSlug }: { orgSlug: string }) {
  const [plans, setPlans] = useState<PlanWithPrices[] | null>(null);
  const [busyPriceId, setBusyPriceId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listPlans()
      .then((result) => {
        if (!cancelled) setPlans(result);
      })
      .catch(() => {
        if (!cancelled) {
          setError("Could not load plans.");
          setPlans([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Choose a plan</CardTitle>
        <CardDescription>Includes a 14-day trial. No card required to start.</CardDescription>
      </CardHeader>
      <CardContent>
        {error ? <p className="mb-2 text-sm text-destructive">{error}</p> : null}
        {plans === null ? (
          <div role="status" aria-label="Loading plans" className="grid gap-4 sm:grid-cols-3">
            {[0, 1, 2].map((card) => (
              <Skeleton key={card} className="h-40 w-full" />
            ))}
          </div>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-3">
            {plans.map((plan) => {
              const price = plan.prices.find((candidate) => candidate.interval === "month");
              if (!price) return null;
              return (
                <li key={plan.id}>
                  <Card className="h-full">
                    <CardHeader>
                      <CardTitle>{plan.name}</CardTitle>
                      <CardDescription>
                        <span className="text-lg font-semibold text-foreground">
                          {formatPrice(price.unit_amount, price.currency)}
                        </span>{" "}
                        / month
                      </CardDescription>
                    </CardHeader>
                    <CardFooter>
                      <Button
                        className="w-full"
                        onClick={() => void checkout(price.id)}
                        disabled={busyPriceId !== null}
                      >
                        {busyPriceId === price.id ? "Starting…" : `Choose ${plan.name}`}
                      </Button>
                    </CardFooter>
                  </Card>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );

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
}
