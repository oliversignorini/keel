"use client";

import { toApexHost } from "@/lib/host";
import { LAST_ORG_STORAGE_KEY } from "@/lib/org/last-org";
import { useOrgContext } from "@/lib/org/org-context";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * `/app` → redirect to last-used organisation (PRD §5 Routes), or
 * `/onboarding` for a user with none yet (PRD §6 "Signup → first
 * organisation": onboarding is where a fresh signup lands, not here).
 * "Last-used" is a `localStorage` preference written by
 * `app/(app)/app/[org]/layout.tsx` every time an organisation actually
 * renders — falls back to the first organisation in `/api/v1/me/`'s list
 * if nothing's stored yet (a brand-new browser, or one that cleared
 * storage).
 */
export default function AppRedirectPage() {
  const router = useRouter();
  const { me, loading } = useOrgContext();

  useEffect(() => {
    if (loading || !me) return;

    if (me.organizations.length === 0) {
      // /onboarding is an (auth) route, reachable only on the apex.
      window.location.href = `${window.location.protocol}//${toApexHost(window.location.host)}/onboarding`;
      return;
    }

    const lastSlug =
      typeof window !== "undefined" ? window.localStorage.getItem(LAST_ORG_STORAGE_KEY) : null;
    const target =
      me.organizations.find((org) => org.slug === lastSlug) ?? me.organizations.at(0) ?? null;
    if (target) {
      router.replace(`/${target.slug}`);
    }
  }, [loading, me, router]);

  return (
    <p role="status" className="text-sm text-neutral-600 dark:text-neutral-400">
      Loading…
    </p>
  );
}
