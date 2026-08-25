"use client";

import { useEffect, useState, type ReactNode } from "react";

import { getCreditBalance } from "@/lib/billing/api";
import { creditsEnabled } from "@/lib/billing/credits-flag";

export interface CreditMeterState {
  /** `null` until the balance has loaded. */
  balance: number | null;
  loading: boolean;
  /** Echoed back from the `estimate` prop, for a render-prop caller that
   * wants to phrase the pre-flight line itself. */
  estimate: number | null;
  /** `true` only once the balance is known *and* an estimate was given
   * that exceeds it — never `true` while loading, so a confirm dialog
   * can't flash a "not enough credits" warning before it knows. */
  insufficient: boolean;
}

interface CreditMeterProps {
  orgSlug: string;
  /**
   * Pre-flight mode (phase-4.md Worktree C: "pre-flight estimate on the
   * confirm dialog"). The dialog itself is Phase 5's — there is no job to
   * confirm yet — so this is a prop a future dialog passes rather than a
   * dialog this component invents. With it set, the meter states the cost
   * against the balance and warns when the balance can't cover it.
   */
  estimate?: number;
  /**
   * Render-prop escape hatch for that same future dialog: given the
   * loaded state, render whatever the dialog needs (a disabled confirm
   * button, its own copy) instead of this component's default chip. The
   * fetch, the flag check, and the 404 handling stay here either way.
   */
  children?: (state: CreditMeterState) => ReactNode;
}

/**
 * The credit balance (PRD §4 "Credits"; phase-4.md Worktree C).
 *
 * Renders **nothing at all** when credits are disabled, and issues no
 * request to find that out — see lib/billing/credits-flag.ts for why the
 * flag is mirrored client-side rather than inferred from the endpoint's
 * 404. The server's 404 is still handled (the flags can drift, and the
 * server's is the real one), and it is handled the same way: render
 * nothing, and do not retry.
 *
 * A 402 is not this component's to catch: credits run out at the moment a
 * job is submitted, not while a meter is being read, so `<CreditMeter>`'s
 * job is to show the number *before* that happens and
 * `<EntitlementGate>`'s (or the submitting action's own error handling)
 * is to react once it has.
 */
export function CreditMeter({ orgSlug, estimate, children }: CreditMeterProps) {
  const [balance, setBalance] = useState<number | null>(null);
  const [loading, setLoading] = useState(creditsEnabled());
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    if (!creditsEnabled()) return;
    let cancelled = false;
    setLoading(true);
    getCreditBalance(orgSlug)
      .then((result) => {
        if (!cancelled) setBalance(result.balance);
      })
      .catch(() => {
        // A 404 means the server's BILLING_CREDITS is off (billing/views.py
        // CreditBalanceView) — "this feature doesn't exist", not "zero
        // credits", so the meter disappears rather than reading 0. Any
        // other failure (403 from a role without billing.view, a network
        // blip) is treated the same way: a balance chip is never worth
        // breaking the page it sits on. Nothing here re-requests.
        if (!cancelled) setUnavailable(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [orgSlug]);

  if (!creditsEnabled() || unavailable) return null;

  const state: CreditMeterState = {
    balance,
    loading,
    estimate: estimate ?? null,
    insufficient: balance !== null && estimate !== undefined && estimate > balance,
  };

  if (children) return <>{children(state)}</>;

  if (loading || balance === null) {
    return (
      <p role="status" className="text-sm text-neutral-500 dark:text-neutral-400">
        Loading credits…
      </p>
    );
  }

  return (
    <p
      className={
        state.insufficient
          ? "text-sm font-medium text-red-700 dark:text-red-400"
          : "text-sm text-neutral-600 dark:text-neutral-400"
      }
    >
      {estimate === undefined ? (
        <>Credits: {balance.toLocaleString()}</>
      ) : (
        <>
          This will use {estimate.toLocaleString()} of your {balance.toLocaleString()} credits
          {state.insufficient ? " — not enough credits" : ""}
        </>
      )}
    </p>
  );
}
