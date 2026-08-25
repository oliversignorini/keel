"use client";

import { UnauthorizedError } from "@keel/api-client";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { getMe } from "./api";
import type { MeResponse } from "./types";

interface UseMeResult {
  me: MeResponse | null;
  loading: boolean;
  /** Re-fetches `/api/v1/me/` — call after creating an organisation,
   * accepting an invitation, or switching organisations, so the client
   * never renders permissions or entitlements from a stale response
   * (phase-3.md Worktree C: "Switching organisation ... refetches all
   * data"). */
  refetch: () => Promise<void>;
}

/**
 * `GET /api/v1/me/` (PRD §7) is what the whole client renders from: the
 * user, their organisations, and — per organisation — the resolved role,
 * permission codes, and entitlements. Like useCurrentUser (Phase 2), the
 * API is the enforcement point; this hook exists to drive *rendering*
 * only, never to gate a request.
 */
export function useMe(): UseMeResult {
  const router = useRouter();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getMe();
      setMe(result);
    } catch (error) {
      if (error instanceof UnauthorizedError) {
        router.push(`/login?next=${encodeURIComponent(window.location.pathname)}`);
        return;
      }
      throw error;
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    // fetchMe is stable across the lifetime of a given router instance
    // (its only dependency, itself stable per Next.js), so this only
    // re-runs if the router identity actually changes — not on every
    // render.
    void fetchMe();
  }, [fetchMe]);

  return { me, loading, refetch: fetchMe };
}
