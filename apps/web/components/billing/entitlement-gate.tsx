"use client";

import { PaymentRequiredError } from "@keel/api-client";
import { Alert, AlertDescription, AlertTitle, Button } from "@keel/ui";
import { Sparkles } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { listPlans } from "@/lib/billing/api";
import { cheapestPlanWithFeature, hasFeature } from "@/lib/billing/entitlements";
import type { PlanWithPrices } from "@/lib/billing/types";
import { useOrgContext } from "@/lib/org/org-context";

interface EntitlementGateContextValue {
  /**
   * Hand a caught error to the gate. A `PaymentRequiredError` for this
   * gate's feature (or one carrying no feature at all) closes the gate
   * and shows the upgrade prompt; anything else is returned as `false` so
   * the caller can rethrow or handle it normally.
   */
  reportError: (error: unknown) => boolean;
}

const EntitlementGateContext = createContext<EntitlementGateContextValue | null>(null);

/**
 * For an action *inside* a gate: pass it whatever your `catch` caught and
 * the surrounding gate flips to the upgrade prompt if the API said 402.
 * Returns `false` outside a gate, so a shared action component can call
 * it unconditionally.
 */
export function useReportEntitlementError(): (error: unknown) => boolean {
  const context = useContext(EntitlementGateContext);
  return useCallback((error: unknown) => context?.reportError(error) ?? false, [context]);
}

interface EntitlementGateProps {
  /** A feature code from `Plan.entitlements.features` — the same string
   * `@requires_entitlement("api_access")` names server-side. */
  feature: string;
  children?: ReactNode;
  /** Rendered instead of the built-in upgrade prompt when the feature is
   * not entitled. */
  fallback?: ReactNode;
}

/**
 * Renders `children` only while the current organisation's resolved
 * entitlements (from `/api/v1/me/`, PRD §7) include `feature`; otherwise
 * an upgrade prompt **naming the plan the visitor needs, not the feature
 * they lack** (phase-4.md Worktree C).
 *
 * PRESENTATION ONLY, exactly like `<Can>` (components/org/can.tsx) — but
 * gating on entitlements rather than permission codes, and with one extra
 * mode `<Can>` has no equivalent for. Entitlements can go stale inside a
 * loaded page in a way permissions rarely do: a trial ends, a card
 * declines, another admin downgrades the plan. So an action inside the
 * gate can hand a caught 402 back with `useReportEntitlementError()` and
 * the gate closes on the spot, without a reload. The API is still the
 * enforcement point in both directions — `billing/entitlements.py` raises
 * 402 whether or not this component ever rendered, which
 * ./entitlement-gate.presentation-only.test.tsx proves by calling the API
 * with the gate removed entirely.
 *
 * There is no real feature to wire this into yet: `check_feature` has no
 * caller in the API outside its own tests, because the feature surface it
 * would gate is Phase 5's. So this ships as a tested component with a
 * fixed props contract, not as a gate around something.
 */
export function EntitlementGate({ feature, children, fallback }: EntitlementGateProps) {
  const { currentOrg, loading } = useOrgContext();
  const [denied, setDenied] = useState(false);

  const entitled = hasFeature(currentOrg, feature) && !denied;

  // A fresh /me (organisation switch, refetch after checkout) supersedes a
  // 402 this gate caught against the previous entitlement list.
  useEffect(() => {
    setDenied(false);
  }, [currentOrg, feature]);

  const reportError = useCallback(
    (error: unknown) => {
      if (!(error instanceof PaymentRequiredError)) return false;
      // `details` is typed as `ApiErrorDetail[]` for allauth's field-error
      // shape, but Keel's own envelope passes `details` through verbatim
      // (packages/api-client/src/http/normalize-envelope.ts), and
      // billing/entitlements.py sends an object: `{"feature": …}` for
      // `feature_not_entitled`, `{"resource": …, "limit": …}` for
      // `limit_exceeded`. A 402 that names a *different* feature or
      // resource belongs to some other gate and is left for the caller;
      // one that names nothing is assumed to be this gate's.
      const details: unknown = error.details;
      const named =
        typeof details === "object" && details !== null && !Array.isArray(details)
          ? ((details as { feature?: string; resource?: string }).feature ??
            (details as { resource?: string }).resource)
          : undefined;
      if (named && named !== feature) return false;
      setDenied(true);
      return true;
    },
    [feature],
  );

  if (loading && !currentOrg) return null;

  if (!entitled) {
    if (fallback !== undefined) return <>{fallback}</>;
    return <UpgradePrompt feature={feature} />;
  }

  return (
    <EntitlementGateContext.Provider value={{ reportError }}>
      {children}
    </EntitlementGateContext.Provider>
  );
}

/**
 * The catalogue is only fetched once a gate has actually closed — the
 * entitled path costs no request. `/api/v1/plans/` is public and
 * unpaginated (billing/viewsets.py `PlanViewSet`), so this works whether
 * or not the visitor can see billing settings.
 */
function UpgradePrompt({ feature }: { feature: string }) {
  const { currentOrg } = useOrgContext();
  const [plans, setPlans] = useState<PlanWithPrices[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    listPlans()
      .then((result) => {
        if (!cancelled) setPlans(result);
      })
      .catch(() => {
        // A generic prompt is a fine outcome; a broken page is not.
        if (!cancelled) setPlans([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const requiredPlan = plans ? cheapestPlanWithFeature(plans, feature) : null;

  // `role="note"` rather than <Alert>'s default `role="alert"`: this
  // renders as part of the page's normal content, not as an interruption.
  return (
    <Alert variant="warning" role="note">
      <Sparkles />
      <AlertTitle>
        {requiredPlan ? `Available on the ${requiredPlan.name} plan.` : "Available on a paid plan."}
      </AlertTitle>
      {currentOrg ? (
        <AlertDescription>
          <Button asChild variant="outline" size="sm">
            <a href={`/${currentOrg.slug}/settings/billing`}>
              {requiredPlan ? `Upgrade to ${requiredPlan.name}` : "View plans"}
            </a>
          </Button>
        </AlertDescription>
      ) : null}
    </Alert>
  );
}
