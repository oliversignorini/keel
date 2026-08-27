/**
 * Server-only Django origins the BFF route handlers (apps/web/app/api/v1/
 * [...path]/route.ts, apps/web/app/api/internal/allauth/[...path]/route.ts)
 * forward to. Deliberately not `NEXT_PUBLIC_*` — docs/adr/0002-auth-bff-shape.md:
 * the whole point is that the browser bundle never needs to know where
 * Django lives any more.
 */

/** Django's sync (gunicorn/runserver) origin — everything except the SSE
 * stream. */
export const API_INTERNAL_ORIGIN = process.env.KEEL_API_INTERNAL_URL ?? "http://api.lvh.me:8000";

/** The dedicated ASGI stream service (PRD §5.5.5) — SSE only, never the
 * sync process; see apps/api/config/asgi_stream.py. */
export const API_STREAM_INTERNAL_ORIGIN =
  process.env.KEEL_API_STREAM_INTERNAL_URL ?? "http://localhost:8001";

const JOB_STREAM_PATH_PATTERN = /\/orgs\/[^/]+\/jobs\/stream\/?$/;

/** True for the one `/api/v1/…` path this proxy routes to the stream
 * service instead of the regular API origin. */
export function isJobStreamPath(path: string): boolean {
  return JOB_STREAM_PATH_PATTERN.test(path);
}
