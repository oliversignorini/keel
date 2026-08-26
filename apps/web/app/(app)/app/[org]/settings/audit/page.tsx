"use client";

import { useCallback, useEffect, useState } from "react";

import { Can } from "@/components/org/can";
import { listAuditLogs } from "@/lib/org/api";
import { useOrgContext } from "@/lib/org/org-context";
import { Perm } from "@/lib/org/permissions";
import { ApiError, type AuditLog } from "@keel/api-client";

/**
 * `/app/[org]/settings/audit` (PRD §5 Routes; PRD §7's audit endpoint;
 * docs/plans/phase-8.md 8.2). Gated by `audit.view` — `<Can>` here is
 * presentation only, same as every other settings tab (components/org/can.tsx):
 * `AuditLogViewSet` enforces `audit.view` server-side regardless of
 * whether this renders.
 */
export default function AuditSettingsPage() {
  const { currentOrg } = useOrgContext();
  const orgSlug = currentOrg?.slug ?? "";
  const [rows, setRows] = useState<AuditLog[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!orgSlug) return;
    setLoading(true);
    setError(null);
    try {
      const page = await listAuditLogs(orgSlug);
      setRows(page.results);
      setNextCursor(page.next);
    } catch (fetchError) {
      setError(
        fetchError instanceof ApiError ? fetchError.message : "Could not load the audit log.",
      );
    } finally {
      setLoading(false);
    }
  }, [orgSlug]);

  useEffect(() => {
    void load();
  }, [load]);

  async function loadMore() {
    if (!nextCursor) return;
    setLoadingMore(true);
    try {
      const page = await listAuditLogs(orgSlug, nextCursor);
      setRows((existing) => [...existing, ...page.results]);
      setNextCursor(page.next);
    } catch (fetchError) {
      setError(fetchError instanceof ApiError ? fetchError.message : "Could not load more.");
    } finally {
      setLoadingMore(false);
    }
  }

  if (!currentOrg) return null;

  return (
    <Can
      code={Perm.AUDIT_VIEW}
      fallback={
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          You do not have permission to view this organisation&apos;s audit log.
        </p>
      }
    >
      <div className="flex flex-col gap-6">
        <div>
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            Audit log
          </h2>
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            Every action taken in this organisation, most recent first.
          </p>
        </div>

        {error ? <p className="text-sm text-red-600 dark:text-red-400">{error}</p> : null}

        {loading ? (
          <p className="text-sm text-neutral-600 dark:text-neutral-400">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-neutral-500 dark:text-neutral-500">
            No activity recorded yet.
          </p>
        ) : (
          <>
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-neutral-200 text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
                  <th className="py-2 font-medium">Action</th>
                  <th className="py-2 font-medium">Actor</th>
                  <th className="py-2 font-medium">Target</th>
                  <th className="py-2 font-medium">When</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b border-neutral-100 dark:border-neutral-900">
                    <td className="py-2 text-neutral-900 dark:text-neutral-100">{row.action}</td>
                    <td className="py-2 text-neutral-700 dark:text-neutral-300">
                      {row.actor ? row.actor.name || row.actor.email : "System"}
                      {row.impersonator ? (
                        <span className="ml-1 text-xs text-amber-600 dark:text-amber-400">
                          (impersonated by {row.impersonator.name || row.impersonator.email})
                        </span>
                      ) : null}
                    </td>
                    <td className="py-2 text-neutral-500 dark:text-neutral-500">
                      {row.target_type ? `${row.target_type} ${row.target_id}` : "—"}
                    </td>
                    <td className="py-2 text-neutral-500 dark:text-neutral-500">
                      {new Date(row.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {nextCursor ? (
              <button
                type="button"
                onClick={() => void loadMore()}
                disabled={loadingMore}
                className="self-start rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium disabled:opacity-50 dark:border-neutral-700"
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            ) : null}
          </>
        )}
      </div>
    </Can>
  );
}
