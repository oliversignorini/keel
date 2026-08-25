/**
 * `Job` / `JobStep` themselves come straight from `@keel/api-client`
 * (`JobViewSet` has a real `serializer_class`, so orval types them fully —
 * see lib/billing/types.ts's docstring for why that means they are not
 * repeated here). What's hand-written below is the SSE payload shape
 * (PRD §5.5.5) — it is not part of the REST schema at all, so orval has
 * nothing to generate it from. Transcribed from
 * apps/api/keel/jobs/pubsub.py's `job_event` / `step_event`.
 */

export interface JobStreamJobEvent {
  type: "job";
  job_id: string;
  status: string;
  job_type: string;
  result_ref: string;
  error: string;
}

export interface JobStreamStepEvent {
  type: "step";
  job_id: string;
  step_id: string;
  name: string;
  ordinal: number;
  status: string;
  output_ref: string;
  error: string;
}

export type JobStreamEvent = JobStreamJobEvent | JobStreamStepEvent;

/** `useJobStream`'s connection state — `"live"` only while the SSE
 * connection is actually open; `"polling"` covers both "never connected"
 * and "dropped and fell back", which is deliberately the same state to
 * the caller (docs/plans/phase-5.5.md 5.5.6: automatic fallback). */
export type JobStreamConnection = "connecting" | "live" | "polling";
