"use client";

import { useCallback, useEffect, useState } from "react";

import { Can } from "@/components/org/can";
import { listAuditLogs } from "@/lib/org/api";
import { useOrgContext } from "@/lib/org/org-context";
import { Perm } from "@/lib/org/permissions";
import { ApiError, type AuditLogOut } from "@keel/api-client";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@keel/ui";
import { Loader2 } from "lucide-react";

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
  const [rows, setRows] = useState<AuditLogOut[]>([]);
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
        <p className="text-sm text-muted-foreground">
          You do not have permission to view this organisation&apos;s audit log.
        </p>
      }
    >
      <Card>
        <CardHeader>
          <CardTitle>Audit log</CardTitle>
          <CardDescription>
            Every action taken in this organisation, most recent first.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {error ? <p className="text-sm text-destructive">{error}</p> : null}

          {loading ? (
            <div className="flex flex-col gap-3" role="status" aria-label="Loading audit log">
              {[0, 1, 2, 3, 4].map((row) => (
                <Skeleton key={row} className="h-6 w-full" />
              ))}
            </div>
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No activity recorded yet.</p>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Action</TableHead>
                    <TableHead>Actor</TableHead>
                    <TableHead>Target</TableHead>
                    <TableHead>When</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell>
                        <Badge variant={actionVariant(row.action)}>{row.action}</Badge>
                      </TableCell>
                      <TableCell className="text-foreground">
                        {row.actor ? row.actor.name || row.actor.email : "System"}
                        {row.impersonator ? (
                          <span className="ml-1 text-xs text-warning">
                            (impersonated by {row.impersonator.name || row.impersonator.email})
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {row.target_type ? `${row.target_type} ${row.target_id}` : "—"}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <time dateTime={row.created_at}>
                              {new Date(row.created_at).toLocaleString()}
                            </time>
                          </TooltipTrigger>
                          <TooltipContent>{new Date(row.created_at).toISOString()}</TooltipContent>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {nextCursor ? (
                <Button
                  variant="outline"
                  onClick={() => void loadMore()}
                  disabled={loadingMore}
                  className="self-start"
                >
                  {loadingMore ? (
                    <>
                      <Loader2 className="animate-spin" />
                      Loading…
                    </>
                  ) : (
                    "Load more"
                  )}
                </Button>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>
    </Can>
  );
}

/** Audit actions are `resource.verb`; the verb is the only part that
 * carries a severity worth colouring. */
function actionVariant(action: string): "secondary" | "destructive" | "success" {
  if (action.endsWith(".deleted") || action.endsWith(".removed") || action.endsWith(".revoked")) {
    return "destructive";
  }
  if (action.endsWith(".created")) return "success";
  return "secondary";
}
