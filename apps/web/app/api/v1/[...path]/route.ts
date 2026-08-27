import type { NextRequest } from "next/server";

import {
  API_INTERNAL_ORIGIN,
  API_STREAM_INTERNAL_ORIGIN,
  isJobStreamPath,
} from "@/lib/api/internal-origins";
import { proxyRequest } from "@/lib/api/proxy";

// Node runtime, not Edge: this streams the SSE job-status response
// (jobs/stream/) through unbuffered via a ReadableStream body, and Edge's
// fetch/Response implementation is not the target this was verified
// against. `force-dynamic` + `revalidate: 0` stop Next.js from ever trying
// to cache a response that is per-session (cookie-scoped) by nature.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const revalidate = 0;

async function handle(request: NextRequest): Promise<Response> {
  // `request.nextUrl.pathname`, not the `[...path]` catch-all params:
  // Django Ninja's routes are all trailing-slash-terminated, and the
  // catch-all segment array collapses a request to `/api/v1/me/` and one
  // to `/api/v1/me` to the same `['me']`, silently dropping the slash —
  // which then earns a redirect loop against Django's own APPEND_SLASH
  // (confirmed live: `/api/v1/me/` proxied as `/api/v1/me`, Django 301s
  // back to `/api/v1/me/`, forwarded slash-less again, forever). Reading
  // the literal pathname preserves whichever form the caller actually
  // used.
  const upstreamPath = request.nextUrl.pathname;
  const upstreamOrigin = isJobStreamPath(upstreamPath)
    ? API_STREAM_INTERNAL_ORIGIN
    : API_INTERNAL_ORIGIN;

  // Already Keel-shaped end to end (keel/core/exceptions.py's envelope) —
  // no transformErrorBody here, unlike the allauth route.
  return proxyRequest(request, { upstreamOrigin, upstreamPath });
}

export async function GET(request: NextRequest) {
  return handle(request);
}
export async function POST(request: NextRequest) {
  return handle(request);
}
export async function PUT(request: NextRequest) {
  return handle(request);
}
export async function PATCH(request: NextRequest) {
  return handle(request);
}
export async function DELETE(request: NextRequest) {
  return handle(request);
}
