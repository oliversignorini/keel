"use client";

import { useJobStream } from "@/lib/jobs/use-job-stream";

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

/**
 * `<JobTray>` (PRD §5 component inventory; docs/plans/phase-5.md 5.6):
 * live job status over SSE via `useJobStream`, which itself covers reload
 * survival (a fresh REST fetch on mount) and polling fallback.
 *
 * Deliberately self-contained — no `<AppShell>` here, per this phase's
 * boundary: Phase 6 owns the shell and mounts this component into it.
 */
export function JobTray({ orgSlug }: JobTrayProps) {
  const { jobs, connection } = useJobStream(orgSlug);

  if (jobs.length === 0) {
    return null;
  }

  return (
    <div data-testid="job-tray" aria-live="polite">
      {connection === "polling" && (
        <div data-testid="job-tray-polling-notice" role="status">
          Live updates unavailable — checking periodically.
        </div>
      )}
      <ul>
        {jobs.map((job) => (
          <li key={job.id} data-testid={`job-tray-item-${job.id}`} data-status={job.status}>
            <span>{job.type}</span>
            <span data-testid={`job-tray-status-${job.id}`}>
              {STATUS_LABEL[job.status ?? ""] ?? job.status}
            </span>
            {job.steps.length > 0 && (
              <ol>
                {job.steps.map((step) => (
                  <li key={step.id} data-testid={`job-tray-step-${step.id}`}>
                    {step.name}: {STATUS_LABEL[step.status ?? ""] ?? step.status}
                  </li>
                ))}
              </ol>
            )}
            {job.status === "failed" && job.error && <p role="alert">{job.error}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
