"use client";

import { cn } from "@/lib/cn";
import { useParams, usePathname } from "next/navigation";
import Link from "next/link";

/**
 * Secondary horizontal tab row (PRD §5 "Layout — top bar navigation":
 * "Settings uses a secondary horizontal tab row rather than a nested
 * sidebar"): General · Members · Roles · Billing · Audit. Audit is
 * Phase 8's (docs/plans/phase-8.md 8.2) — the fifth tab PRD §5 lists.
 */
const TABS = [
  { slug: "general", label: "General" },
  { slug: "members", label: "Members" },
  { slug: "roles", label: "Roles" },
  { slug: "billing", label: "Billing" },
  { slug: "audit", label: "Audit" },
] as const;

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ org: string }>();
  const pathname = usePathname();

  return (
    <div>
      <nav className="mb-6 flex gap-1 border-b border-neutral-200 dark:border-neutral-800">
        {TABS.map((tab) => {
          const href = `/${params.org}/settings/${tab.slug}`;
          const active = pathname === href;
          return (
            <Link
              key={tab.slug}
              href={href}
              className={cn(
                "border-b-2 px-3 py-2 text-sm font-medium",
                active
                  ? "border-neutral-900 text-neutral-900 dark:border-neutral-100 dark:text-neutral-100"
                  : "border-transparent text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100",
              )}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>
      {children}
    </div>
  );
}
