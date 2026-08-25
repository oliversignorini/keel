"use client";

import { useCallback, useEffect, useState } from "react";

import { getSubscription } from "./api";
import type { Subscription } from "./types";

interface UseSubscriptionResult {
  /** `null` both while loading and when the organisation has never
   * checked out — `loading` distinguishes them. */
  subscription: Subscription | null;
  loading: boolean;
  /** `true` when the endpoint could not be read at all (a role without
   * `billing.view` gets a 403). Callers render nothing rather than an
   * error: not being allowed to see billing is a normal state, not a
   * fault. */
  unavailable: boolean;
  refetch: () => Promise<void>;
}

/**
 * `GET /organizations/{slug}/billing/subscription/` (PRD §7), which is
 * what both banners and the billing settings page render from.
 *
 * Deliberately not read from `/api/v1/me/`: `me` carries resolved
 * *entitlements* (what the plan allows), not subscription *state* (status,
 * period end, trial end, cancel-at-period-end), and the banners key on
 * state.
 */
export function useSubscription(orgSlug: string): UseSubscriptionResult {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);

  const fetchSubscription = useCallback(async () => {
    if (!orgSlug) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const result = await getSubscription(orgSlug);
      setSubscription(result.subscription);
      setUnavailable(false);
    } catch {
      setSubscription(null);
      setUnavailable(true);
    } finally {
      setLoading(false);
    }
  }, [orgSlug]);

  useEffect(() => {
    void fetchSubscription();
  }, [fetchSubscription]);

  return { subscription, loading, unavailable, refetch: fetchSubscription };
}
