"use client";

import { useOrgContext } from "@/lib/org/org-context";
import { PageHeader } from "@keel/ui";
import Link from "next/link";

/** `/[org]` dashboard (PRD §5 Routes; docs/plans/phase-6.md 6.B). */
export default function OrgDashboardPage() {
  const { currentOrg } = useOrgContext();

  if (!currentOrg) return null;

  return (
    <div>
      <PageHeader
        title={currentOrg.name}
        description={`Signed in as ${currentOrg.role ?? "member"}.`}
      />
      <Link
        href={`/${currentOrg.slug}/widgets`}
        className="text-sm font-medium text-primary underline"
      >
        View widgets →
      </Link>
    </div>
  );
}
