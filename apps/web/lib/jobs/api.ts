/**
 * Thin, typed wrappers around the generated jobs client — the same shape,
 * and for the same reasons, as lib/billing/api.ts and lib/files/api.ts.
 */

import {
  unwrapData,
  cancelJob as generatedCancelJob,
  createJob as generatedCreateJob,
  listJobs as generatedListJobs,
  retrieveJob,
  type JobOut,
} from "@keel/api-client";

export type Job = JobOut;

/** Requires `jobs.view`. Cursor-paginated; `useJobStream` reads every
 * page's worth the tray needs to reconcile with on mount/reload. */
export async function listJobs(orgSlug: string): Promise<Job[]> {
  const result = await generatedListJobs(orgSlug);
  return unwrapData(result).results;
}

/** Requires `jobs.create`. `idempotencyKey`, when given, is honoured by
 * `keel.jobs.idempotency.IdempotencyKeyMiddleware` — replaying the same
 * key returns the original job. */
export async function createJob(
  orgSlug: string,
  body: { type: string; params?: Record<string, unknown> },
  idempotencyKey?: string,
): Promise<Job> {
  const result = await generatedCreateJob(orgSlug, body as never, {
    headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
  });
  return unwrapData(result);
}

/** Requires `jobs.view`. The polling-fallback primitive `useJobStream`
 * calls on an interval once the SSE connection has dropped. */
export async function getJob(orgSlug: string, jobId: string): Promise<Job> {
  const result = await retrieveJob(orgSlug, jobId);
  return unwrapData(result);
}

/** Requires `jobs.create`. */
export async function cancelJob(orgSlug: string, jobId: string): Promise<Job> {
  const result = await generatedCancelJob(orgSlug, jobId, {});
  return unwrapData(result);
}

/** `GET .../jobs/stream/` — SSE. Same-origin relative path
 * (docs/adr/0002-auth-bff-shape.md): the BFF proxy
 * (apps/web/app/api/v1/[...path]/route.ts) detects this exact path shape
 * and forwards it to the dedicated stream service instead of the sync
 * API origin — see `apps/web/lib/api/internal-origins.ts` and
 * `apps/api/config/asgi_stream.py`'s docstring for why that service has
 * to stay separate from gunicorn's sync worker pool (PRD §5.5.5 footgun
 * 1). The browser no longer needs to know that split exists. */
export function jobStreamUrl(orgSlug: string): string {
  return `/api/v1/orgs/${orgSlug}/jobs/stream/`;
}
