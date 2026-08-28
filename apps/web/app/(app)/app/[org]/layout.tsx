"use client";

import { BillingBanners } from "@/components/billing/billing-banners";
import { NotFound } from "@/components/org/not-found";
import { rememberLastOrg } from "@/lib/org/last-org";
import { useOrgContext } from "@/lib/org/org-context";
import { Skeleton } from "@keel/ui";
import { useEffect } from "react";

/**
 * Guards every `/app/[org]/*` route. `useOrgContext().currentOrg` is
 * looked up from `/api/v1/me/`'s organisation list (see
 * lib/org/org-context.tsx) rather than fetched by slug directly — the API
 * already makes a non-member and a nonexistent slug indistinguishable at
 * `GET /api/v1/orgs/{slug}/` (both 404, PRD §6 "Permission
 * denial": "Wrong organisation → 404, never 403. Existence is not
 * disclosed across tenant boundaries"), and deriving the client's notion
 * of membership from the same list the switcher renders keeps that
 * property rather than risking a second code path that leaks it back.
 *
 * A slug absent from `me.organizations` renders the same "not found" panel
 * a real 404 would, rather than redirecting — redirecting to /app would
 * silently swap the visitor into a different organisation, which is
 * exactly the "wrong data" confusion PRD §5 calls out.
 */
export default function OrgLayout({ children }: { children: React.ReactNode }) {
  const { me, loading, currentOrg } = useOrgContext();

  useEffect(() => {
    if (currentOrg) {
      rememberLastOrg(currentOrg.slug);
    }
  }, [currentOrg]);

  if (loading) {
    return (
      <div role="status" aria-label="Loading" className="flex flex-col gap-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (me && !currentOrg) {
    return <NotFound title="Organisation not found" />;
  }

  return (
    <>
      {/* Billing banners live here, not on the billing settings page, so a
          trial ending or a failed payment is visible while the product is
          being used — see components/billing/billing-banners.tsx. */}
      {currentOrg ? <BillingBanners orgSlug={currentOrg.slug} /> : null}
      {children}
    </>
  );
}
