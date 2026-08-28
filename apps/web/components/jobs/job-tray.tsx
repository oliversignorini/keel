"use client";

import { useJobStream } from "@/lib/jobs/use-job-stream";
import { Alert, AlertDescription, Badge, Progress } from "@keel/ui";
import { CheckCircle2, ChevronDown, ChevronUp, Loader2, WifiOff, XCircle } from "lucide-react";
import { useState } from "react";

interface JobTrayProps {
  orgSlug: string;
}

const STATUS_LABEL: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Succeeded",
  partial: "Partial",
  failed: "Failed",
};

type JobBadge = {
  variant: "secondary" | "default" | "success" | "warning" | "destructive";
  icon: typeof Loader2;
};

const DEFAULT_BADGE: JobBadge = { variant: "secondary", icon: Loader2 };

const STATUS_BADGE: Record<string, JobBadge> = {
  queued: DEFAULT_BADGE,
  running: { variant: "default", icon: Loader2 },
  succeeded: { variant: "success", icon: CheckCircle2 },
  partial: { variant: "warning", icon: CheckCircle2 },
  failed: { variant: "destructive", icon: XCircle },
};

function jobProgress(job: { steps: { status: string | null }[] }): number {
  if (job.steps.length === 0) return 0;
  const finished = job.steps.filter(
    (step) => step.status === "succeeded" || step.status === "failed",
  ).length;
  return Math.round((finished / job.steps.length) * 100);
}

/**
 * `<JobTray>` (PRD §5 component inventory; docs/plans/phase-5.md 5.6):
 * live job status over SSE via `useJobStream`, which itself covers reload
 * survival (a fresh REST fetch on mount) and polling fallback.
 *
 * A fixed, collapsible panel rather than a modal `<Sheet>` — jobs are
 * ambient background status the user glances at without losing their
 * place in the page underneath, so content stays mounted (just
 * collapsed) instead of living behind a dialog portal.
 */
export function JobTray({ orgSlug }: JobTrayProps) {
  const { jobs, connection } = useJobStream(orgSlug);
  const [collapsed, setCollapsed] = useState(false);

  if (jobs.length === 0) {
    return null;
  }

  const activeCount = jobs.filter(
    (job) => job.status === "queued" || job.status === "running",
  ).length;

  return (
    <div
      data-testid="job-tray"
      aria-live="polite"
      className="fixed bottom-4 right-4 z-40 w-80 max-w-[calc(100vw-2rem)] rounded-lg border border-border bg-card text-card-foreground shadow-lg"
    >
      <button
        type="button"
        onClick={() => setCollapsed((value) => !value)}
        aria-expanded={!collapsed}
        className="flex w-full items-center gap-2 rounded-t-lg px-3 py-2 text-left text-sm font-medium hover:bg-accent"
      >
        {activeCount > 0 ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <CheckCircle2 className="size-4" />
        )}
        <span className="flex-1">Jobs</span>
        <Badge variant="secondary">{jobs.length}</Badge>
        {collapsed ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
      </button>

      {!collapsed && (
        <div className="flex max-h-80 flex-col gap-3 overflow-y-auto border-t border-border p-3">
          {connection === "polling" && (
            <Alert variant="warning" data-testid="job-tray-polling-notice">
              <WifiOff />
              <AlertDescription>Live updates unavailable — checking periodically.</AlertDescription>
            </Alert>
          )}

          <ul className="flex flex-col gap-3">
            {jobs.map((job) => {
              const badge = STATUS_BADGE[job.status ?? ""] ?? DEFAULT_BADGE;
              const StatusIcon = badge.icon;
              return (
                <li
                  key={job.id}
                  data-testid={`job-tray-item-${job.id}`}
                  data-status={job.status}
                  className="rounded-md border border-border p-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium">{job.type}</span>
                    <Badge variant={badge.variant} data-testid={`job-tray-status-${job.id}`}>
                      <StatusIcon
                        className={job.status === "running" ? "size-3 animate-spin" : "size-3"}
                      />
                      {STATUS_LABEL[job.status ?? ""] ?? job.status}
                    </Badge>
                  </div>

                  {job.steps.length > 0 && (
                    <div className="mt-2 flex flex-col gap-1">
                      <Progress value={jobProgress(job)} className="h-1.5" />
                      <ol className="flex flex-col gap-0.5 text-xs text-muted-foreground">
                        {job.steps.map((step) => (
                          <li key={step.id} data-testid={`job-tray-step-${step.id}`}>
                            {step.name}: {STATUS_LABEL[step.status ?? ""] ?? step.status}
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {job.status === "failed" && job.error && (
                    <Alert variant="destructive" className="mt-2">
                      <XCircle />
                      <AlertDescription>{job.error}</AlertDescription>
                    </Alert>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
