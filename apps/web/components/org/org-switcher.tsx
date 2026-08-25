"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { cn } from "@/lib/cn";
import { useOrgContext } from "@/lib/org/org-context";

/**
 * Dropdown with create-new (keel-prd.md §5 component inventory), placed
 * immediately after the logo in app/(app)/layout.tsx so tenant context is
 * always visible (§5 "Layout — top bar navigation"). Phase 6 owns
 * `<AppShell>`; this is the "minimum honest layout" phase-3.md asks
 * Worktree C for — Phase 6 will likely fold this into the shell rather
 * than replace it outright, since the switcher itself is this worktree's
 * deliverable.
 *
 * Switching organisation pushes the new `/app/[org]` route and lets
 * `<OrgProvider>` refetch `/api/v1/me/` for it (phase-3.md: "Switching
 * organisation updates the route and refetches all data") — no client
 * state carries over between organisations.
 */
export function OrgSwitcher() {
  const router = useRouter();
  const { me, currentOrg } = useOrgContext();
  const [open, setOpen] = useState(false);

  if (!me) {
    return <div className="h-8 w-32 animate-pulse rounded-md bg-neutral-200 dark:bg-neutral-800" />;
  }

  function switchTo(slug: string) {
    setOpen(false);
    router.push(`/app/${slug}`);
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm font-medium text-neutral-900 hover:bg-neutral-100 dark:text-neutral-100 dark:hover:bg-neutral-800"
      >
        {currentOrg?.name ?? "Select organisation"}
        <span aria-hidden="true">▾</span>
      </button>

      {open ? (
        <div
          role="listbox"
          className="absolute left-0 top-full z-10 mt-1 w-56 rounded-md border border-neutral-200 bg-white py-1 shadow-lg dark:border-neutral-800 dark:bg-neutral-900"
        >
          {me.organizations.map((org) => (
            <button
              key={org.id}
              type="button"
              role="option"
              aria-selected={org.slug === currentOrg?.slug}
              onClick={() => switchTo(org.slug)}
              className={cn(
                "block w-full px-3 py-1.5 text-left text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800",
                org.slug === currentOrg?.slug && "font-medium",
              )}
            >
              {org.name}
            </button>
          ))}
          <div className="my-1 border-t border-neutral-200 dark:border-neutral-800" />
          <Link
            href="/onboarding"
            onClick={() => setOpen(false)}
            className="block px-3 py-1.5 text-left text-sm text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
          >
            + Create organisation
          </Link>
        </div>
      ) : null}
    </div>
  );
}
