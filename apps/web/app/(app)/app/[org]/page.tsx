"use client";

import { useOrgContext } from "@/lib/org/org-context";

/**
 * `/app/[org]` dashboard. Phase 6 owns the real dashboard (widget list,
 * `<DataTable>`, `<EmptyState>`) — this is a placeholder that proves the
 * organisation resolved and its role/permissions are visible, which is
 * everything Worktree C's own acceptance needs from this route.
 */
export default function OrgDashboardPage() {
  const { currentOrg } = useOrgContext();

  if (!currentOrg) return null;

  return (
    <div>
      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
        {currentOrg.name}
      </h1>
      <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
        Signed in as {currentOrg.role ?? "member"}.
      </p>
    </div>
  );
}
