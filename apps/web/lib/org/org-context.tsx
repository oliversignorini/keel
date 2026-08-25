"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";

import { useMe } from "./use-me";
import type { MeOrganization, MeResponse } from "./types";

interface OrgContextValue {
  me: MeResponse | null;
  loading: boolean;
  /** The organisation named by the `[org]` route segment, resolved out of
   * `me.organizations` — never fetched separately, so it always carries
   * the same permission list `<Can>` reads (see ./can.tsx). `null` while
   * `me` is still loading, and also `null` if the slug isn't one of the
   * caller's organisations — the layout that resolves this redirects on
   * that case rather than rendering with a null org (see
   * app/(app)/app/[org]/layout.tsx). */
  currentOrg: MeOrganization | null;
  refetch: () => Promise<void>;
}

const OrgContext = createContext<OrgContextValue | null>(null);

export function OrgProvider({ orgSlug, children }: { orgSlug: string; children: ReactNode }) {
  const { me, loading, refetch } = useMe();

  const currentOrg = useMemo(
    () => me?.organizations.find((org) => org.slug === orgSlug) ?? null,
    [me, orgSlug],
  );

  const value = useMemo(
    () => ({ me, loading, currentOrg, refetch }),
    [me, loading, currentOrg, refetch],
  );

  return <OrgContext.Provider value={value}>{children}</OrgContext.Provider>;
}

export function useOrgContext(): OrgContextValue {
  const context = useContext(OrgContext);
  if (!context) {
    throw new Error("useOrgContext must be used inside <OrgProvider>");
  }
  return context;
}
