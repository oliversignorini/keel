"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Box, FileClock, Users } from "lucide-react";

import { useOrgContext } from "@/lib/org/org-context";
import { Perm } from "@/lib/org/permissions";
import { listMembers, listAuditLogs } from "@/lib/org/api";
import type { AuditLogOut, MembershipOut } from "@keel/api-client";
import { listWidgets } from "@/lib/widgets/api";
import type { WidgetOut } from "@keel/api-client";
import { useSubscription } from "@/lib/billing/use-subscription";
import { formatDate } from "@/lib/billing/format";
import { Badge, Card, CardContent, CardHeader, CardTitle, PageHeader, Skeleton } from "@keel/ui";

const WIDGET_STATUS_VARIANT: Record<string, "default" | "secondary" | "outline"> = {
  active: "default",
  draft: "secondary",
  paused: "outline",
};

/** `/[org]` dashboard (PRD §5 Routes; docs/plans/phase-6.md 6.B) — a
 * `<Card>` grid over the four data sources already fetched elsewhere in
 * the product (finding 28), rather than the single "View widgets →"
 * link this route shipped with. */
export default function OrgDashboardPage() {
  const { currentOrg } = useOrgContext();
  const orgSlug = currentOrg?.slug;

  const [widgets, setWidgets] = useState<WidgetOut[] | null>(null);
  const [widgetCount, setWidgetCount] = useState<number | null>(null);
  const [members, setMembers] = useState<MembershipOut[] | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogOut[] | null>(null);

  const canViewWidgets = currentOrg?.permissions.includes(Perm.WIDGETS_VIEW) ?? false;
  const canViewMembers = currentOrg?.permissions.includes(Perm.MEMBERS_VIEW) ?? false;
  const canViewAudit = currentOrg?.permissions.includes(Perm.AUDIT_VIEW) ?? false;
  const canViewBilling = currentOrg?.permissions.includes(Perm.BILLING_VIEW) ?? false;

  const { subscription, loading: subscriptionLoading } = useSubscription(
    canViewBilling ? (orgSlug ?? "") : "",
  );

  useEffect(() => {
    if (!orgSlug || !canViewWidgets) return;
    let cancelled = false;
    listWidgets(orgSlug).then((page) => {
      if (cancelled) return;
      setWidgets(page.results.slice(0, 5));
      setWidgetCount(page.results.length);
    });
    return () => {
      cancelled = true;
    };
  }, [orgSlug, canViewWidgets]);

  useEffect(() => {
    if (!orgSlug || !canViewMembers) return;
    let cancelled = false;
    listMembers(orgSlug).then((result) => {
      if (!cancelled) setMembers(result);
    });
    return () => {
      cancelled = true;
    };
  }, [orgSlug, canViewMembers]);

  useEffect(() => {
    if (!orgSlug || !canViewAudit) return;
    let cancelled = false;
    listAuditLogs(orgSlug).then((page) => {
      if (!cancelled) setAuditLogs(page.results.slice(0, 5));
    });
    return () => {
      cancelled = true;
    };
  }, [orgSlug, canViewAudit]);

  if (!currentOrg) return null;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={currentOrg.name}
        description={`Signed in as ${currentOrg.role ?? "member"}.`}
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
              <Box className="size-4" />
              Widgets
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!canViewWidgets ? (
              <p className="text-sm text-muted-foreground">No access.</p>
            ) : widgetCount === null ? (
              <Skeleton className="h-8 w-12" />
            ) : (
              <p className="text-2xl font-semibold">{widgetCount}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
              <Users className="size-4" />
              Members
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!canViewMembers ? (
              <p className="text-sm text-muted-foreground">No access.</p>
            ) : members === null ? (
              <Skeleton className="h-8 w-12" />
            ) : (
              <p className="text-2xl font-semibold">{members.length}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Plan</CardTitle>
          </CardHeader>
          <CardContent>
            {!canViewBilling ? (
              <p className="text-sm text-muted-foreground">No access.</p>
            ) : subscriptionLoading ? (
              <Skeleton className="h-8 w-20" />
            ) : subscription ? (
              <div className="flex items-center gap-2">
                <p className="text-lg font-semibold capitalize">{subscription.plan}</p>
                <Badge variant="outline" className="capitalize">
                  {subscription.status.replace("_", " ")}
                </Badge>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No subscription.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
              <FileClock className="size-4" />
              Last activity
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!canViewAudit ? (
              <p className="text-sm text-muted-foreground">No access.</p>
            ) : auditLogs === null ? (
              <Skeleton className="h-8 w-24" />
            ) : !auditLogs[0] ? (
              <p className="text-sm text-muted-foreground">None yet.</p>
            ) : (
              <p className="text-sm font-semibold">{formatDate(auditLogs[0].created_at)}</p>
            )}
          </CardContent>
        </Card>
      </div>

      {canViewWidgets && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Recent widgets</CardTitle>
            <Link
              href={`/${currentOrg.slug}/widgets`}
              className="flex items-center gap-1 text-sm font-medium text-primary hover:underline"
            >
              View all
              <ArrowRight className="size-4" />
            </Link>
          </CardHeader>
          <CardContent>
            {widgets === null ? (
              <div className="flex flex-col gap-2">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
              </div>
            ) : widgets.length === 0 ? (
              <p className="text-sm text-muted-foreground">No widgets yet.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {widgets.map((widget) => (
                  <li key={widget.id} className="flex items-center justify-between text-sm">
                    <Link
                      href={`/${currentOrg.slug}/widgets/${widget.id}`}
                      className="text-foreground hover:underline"
                    >
                      {widget.name}
                    </Link>
                    <Badge variant={WIDGET_STATUS_VARIANT[widget.status] ?? "outline"}>
                      {widget.status}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      {canViewAudit && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Recent audit entries</CardTitle>
            <Link
              href={`/${currentOrg.slug}/settings/audit`}
              className="flex items-center gap-1 text-sm font-medium text-primary hover:underline"
            >
              View all
              <ArrowRight className="size-4" />
            </Link>
          </CardHeader>
          <CardContent>
            {auditLogs === null ? (
              <div className="flex flex-col gap-2">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
              </div>
            ) : auditLogs.length === 0 ? (
              <p className="text-sm text-muted-foreground">No activity yet.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {auditLogs.map((entry) => (
                  <li key={entry.id} className="flex items-center justify-between text-sm">
                    <span className="text-foreground">{entry.action}</span>
                    <span className="text-muted-foreground">{formatDate(entry.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
