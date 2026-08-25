"use client";

import { useEffect, useRef, useState } from "react";

import type { Job } from "@keel/api-client";

import { getJob, jobStreamUrl, listJobs } from "./api";
import type { JobStreamConnection, JobStreamEvent } from "./types";

const POLL_INTERVAL_MS = 4_000;
const TERMINAL_STATUSES = new Set(["succeeded", "partial", "failed"]);

interface UseJobStreamResult {
  jobs: Job[];
  /** `"live"` only while the SSE connection is actually open. `"polling"`
   * covers both "never connected yet" and "dropped and fell back" —
   * deliberately the same state to a caller, since both render the same
   * "not currently streaming" affordance. */
  connection: JobStreamConnection;
}

function applyJobEvent(
  jobs: Map<string, Job>,
  event: Extract<JobStreamEvent, { type: "job" }>,
): void {
  const existing = jobs.get(event.job_id);
  jobs.set(event.job_id, {
    ...(existing as Job),
    id: event.job_id,
    type: event.job_type,
    status: event.status as Job["status"],
    result_ref: event.result_ref,
    error: event.error,
    steps: existing?.steps ?? [],
  });
}

function applyStepEvent(
  jobs: Map<string, Job>,
  event: Extract<JobStreamEvent, { type: "step" }>,
): void {
  const existing = jobs.get(event.job_id);
  if (!existing) {
    // A step for a job this tab hasn't fetched yet (e.g. created from
    // another tab moments ago) — the next poll/reconnect's listJobs()
    // call picks it up; nothing to merge the step into yet.
    return;
  }
  const steps = existing.steps.filter((step) => step.id !== event.step_id);
  steps.push({
    id: event.step_id,
    name: event.name,
    ordinal: event.ordinal,
    status: event.status as Job["steps"][number]["status"],
    output_ref: event.output_ref,
    error: event.error,
    started_at: null,
    finished_at: null,
  });
  steps.sort((a, b) => a.ordinal - b.ordinal);
  jobs.set(event.job_id, { ...existing, steps });
}

/**
 * `useJobStream` (PRD §5.5.6): reconciles from the REST list on mount —
 * which is what makes a full page reload with jobs still running correct
 * (docs/plans/phase-5.5.md acceptance) — then subscribes to SSE for live
 * step transitions, falling back to polling automatically when the
 * connection drops or never opens (e.g. an ad blocker, a proxy that
 * doesn't support SSE). `EventSource` itself already retries the
 * underlying connection; polling only covers the *gap* while it's down,
 * and stops the moment `onopen` fires again.
 */
export function useJobStream(orgSlug: string | undefined): UseJobStreamResult {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [connection, setConnection] = useState<JobStreamConnection>("connecting");
  const jobsRef = useRef<Map<string, Job>>(new Map());

  useEffect(() => {
    if (!orgSlug) {
      return undefined;
    }

    let cancelled = false;
    let pollTimer: ReturnType<typeof setInterval> | undefined;
    let eventSource: EventSource | undefined;

    const publish = () => {
      if (!cancelled) {
        setJobs(Array.from(jobsRef.current.values()));
      }
    };

    const reconcile = async () => {
      try {
        const list = await listJobs(orgSlug);
        if (cancelled) return;
        jobsRef.current = new Map(list.map((job) => [job.id, job]));
        publish();
      } catch {
        // Transient — the next poll tick or SSE reconnect tries again.
      }
    };

    const pollOne = async (jobId: string) => {
      try {
        const job = await getJob(orgSlug, jobId);
        if (cancelled) return;
        jobsRef.current.set(jobId, job);
        publish();
      } catch {
        // Transient — next tick retries.
      }
    };

    const startPolling = () => {
      setConnection("polling");
      if (pollTimer) return;
      pollTimer = setInterval(() => {
        for (const job of jobsRef.current.values()) {
          if (!TERMINAL_STATUSES.has(job.status ?? "")) {
            void pollOne(job.id);
          }
        }
      }, POLL_INTERVAL_MS);
    };

    const stopPolling = () => {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = undefined;
      }
    };

    const connect = () => {
      eventSource = new EventSource(jobStreamUrl(orgSlug), { withCredentials: true });

      eventSource.addEventListener("job", (raw) => {
        try {
          const event = JSON.parse((raw as MessageEvent<string>).data) as JobStreamEvent;
          if (event.type === "job") {
            applyJobEvent(jobsRef.current, event);
          } else {
            applyStepEvent(jobsRef.current, event);
          }
          publish();
        } catch {
          // A malformed event is dropped, not fatal to the connection.
        }
      });

      eventSource.onopen = () => {
        if (cancelled) return;
        setConnection("live");
        stopPolling();
      };

      eventSource.onerror = () => {
        if (cancelled) return;
        startPolling();
      };
    };

    void reconcile().then(() => {
      if (!cancelled) connect();
    });

    return () => {
      cancelled = true;
      eventSource?.close();
      stopPolling();
    };
  }, [orgSlug]);

  return { jobs, connection };
}
