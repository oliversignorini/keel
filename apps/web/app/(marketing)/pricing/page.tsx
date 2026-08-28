import type { Metadata } from "next";

import { PricingTable } from "./pricing-table";
import { listPlans } from "@/lib/billing/api";
import type { PlanWithPrices } from "@/lib/billing/types";

export const metadata: Metadata = {
  title: "Pricing — Keel",
};

/**
 * Incrementally regenerated rather than client-fetched: phase-4.md
 * Worktree C asks for the pricing page to be "static where it can be, so
 * PRD Phase 7's Lighthouse gate stays reachable", and a `useEffect` fetch
 * would put the page's entire reason for existing behind a spinner and a
 * round trip. `GET /api/v1/plans/` is public (`PlanViewSet` is AllowAny),
 * so the render needs no session and no cookie — the one property that
 * makes this cacheable at all.
 *
 * An hour is well inside "Stripe is the source of truth, local rows are a
 * cache refreshed nightly" (phase-4.md B.1) — the page can never be more
 * stale than the table it reads.
 */
export const revalidate = 3600;

/** Outside the `(app)` and `(auth)` route groups on purpose: this is the
 * one marketing page in the app, with no shell, no organisation, and no
 * session. */
export default async function PricingPage() {
  let plans: PlanWithPrices[] = [];
  let failed = false;
  try {
    plans = await listPlans();
  } catch {
    // A build or revalidation that can't reach the API must not fail the
    // whole route — the page degrades to its copy plus a link to sign up.
    failed = true;
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-16">
      <h1 className="text-3xl font-semibold text-foreground">Pricing</h1>
      <p className="mt-2 text-muted-foreground">
        Every plan includes a 14-day trial. No card required to start.
      </p>
      {failed ? (
        <p className="mt-8 text-sm text-muted-foreground">
          Plans are temporarily unavailable. Please try again shortly.
        </p>
      ) : (
        <PricingTable plans={plans} />
      )}
    </main>
  );
}
