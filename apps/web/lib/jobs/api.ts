/**
 * Thin, typed wrappers around the generated jobs client — the same shape,
 * and for the same reasons, as lib/billing/api.ts and lib/files/api.ts.
 */

import {
  organizationsJobsCancelCreate,
  organizationsJobsCreate,
  organizationsJobsList,
  organizationsJobsRetrieve,
  type Job,
} from "@keel/api-client";

/**
 * The dedicated ASGI service's origin (PRD §4 system architecture; §5.5.5
 * footgun 1 — SSE must never share gunicorn's sync worker pool). Same
 * hostname as the API via path routing in production; a distinct port in
 * dev, where nothing does that routing for you — see
 * `apps/api/config/asgi_stream.py`'s docstring for how to run it
 * (`uvicorn config.asgi_stream:application --port 8001`).
 */
export const API_STREAM_URL = process.env.NEXT_PUBLIC_API_STREAM_URL ?? "http://localhost:8001";

/** Requires `jobs.view`. Cursor-paginated; `useJobStream` reads every
 * page's worth the tray needs to reconcile with on mount/reload. */
export async function listJobs(orgSlug: string): Promise<Job[]> {
  const result = await organizationsJobsList(orgSlug);
  return result.data.results;
}

/** Requires `jobs.create`. `idempotencyKey`, when given, is honoured by
 * `keel.jobs.idempotency.IdempotencyKeyMiddleware` — replaying the same
 * key returns the original job. */
export async function createJob(
  orgSlug: string,
  body: { type: string; params?: Record<string, unknown> },
  idempotencyKey?: string,
): Promise<Job> {
  const result = await organizationsJobsCreate(orgSlug, body as Job, {
    headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
  });
  return result.data;
}

/** Requires `jobs.view`. The polling-fallback primitive `useJobStream`
 * calls on an interval once the SSE connection has dropped. */
export async function getJob(orgSlug: string, jobId: string): Promise<Job> {
  const result = await organizationsJobsRetrieve(orgSlug, jobId);
  return result.data;
}

/** Requires `jobs.create`. */
export async function cancelJob(orgSlug: string, jobId: string): Promise<Job> {
  const result = await organizationsJobsCancelCreate(orgSlug, jobId, {} as Job);
  return result.data;
}

/** `GET .../jobs/stream/` — SSE, served only by the stream service
 * (`config/urls_stream.py`), never by `API_BASE_URL`'s sync process. */
export function jobStreamUrl(orgSlug: string): string {
  return `${API_STREAM_URL}/api/v1/organizations/${orgSlug}/jobs/stream/`;
}
