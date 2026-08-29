"use client";

import { UnauthorizedError } from "@keel/api-client";
import { useCallback, useEffect, useState } from "react";

import { toApexHost } from "@/lib/host";

import { getMe } from "./api";
import type { MeResponse } from "./types";

interface UseMeResult {
  me: MeResponse | null;
  loading: boolean;
  /** Re-fetches `/api/v1/me/` — call after creating an organisation,
   * accepting an invitation, or switching organisations, so the client
   * never renders permissions or entitlements from a stale response —
   * switching organisation must refetch all data. */
  refetch: () => Promise<void>;
}

/**
 * `GET /api/v1/me/` is what the whole client renders from: the
 * user, their organisations, and — per organisation — the resolved role,
 * permission codes, and entitlements. Like useCurrentUser, the
 * API is the enforcement point; this hook exists to drive *rendering*
 * only, never to gate a request.
 */
export function useMe(): UseMeResult {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getMe();
      setMe(result);
    } catch (error) {
      if (error instanceof UnauthorizedError) {
        // /login only exists on the apex (plan 6.A) — this hook is used
        // from the app host, so getting there is a real navigation, not
        // router.push, and `next` has to carry the full current URL back
        // across hosts.
        const apexOrigin = `${window.location.protocol}//${toApexHost(window.location.host)}`;
        window.location.href = `${apexOrigin}/login?next=${encodeURIComponent(window.location.href)}`;
        return;
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchMe();
  }, [fetchMe]);

  return { me, loading, refetch: fetchMe };
}
