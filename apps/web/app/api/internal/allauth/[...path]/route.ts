import { normalizeErrorEnvelope } from "@keel/api-client";
import type { NextRequest } from "next/server";

import { API_INTERNAL_ORIGIN } from "@/lib/api/internal-origins";
import { proxyRequest } from "@/lib/api/proxy";

// Reached via middleware.ts's rewrite of `/_allauth/:path*` to
// `/api/internal/allauth/:path*` — Next.js treats a literal `app/_allauth`
// folder as an unrouted "private folder" (the leading underscore is a
// framework convention), so this is what lets the wire path the browser
// actually calls stay `/_allauth/…` (docs/adr/0002-auth-bff-shape.md).
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const revalidate = 0;

async function handle(request: NextRequest): Promise<Response> {
  // `request.nextUrl.pathname` reflects the *original*, pre-rewrite
  // request path here (`/_allauth/…`) rather than the rewritten
  // `/api/internal/allauth/…` this handler is mounted at — verified live
  // (a naive "strip the /api/internal/allauth prefix" produced garbage:
  // the pathname was never prefixed with it to begin with). That's
  // actually exactly the path Django wants, so no rewriting is needed
  // here at all — see apps/web/app/api/v1/[...path]/route.ts's comment
  // for why this is the pathname and not the `[...path]` catch-all
  // params (trailing-slash preservation).
  const upstreamPath = request.nextUrl.pathname;

  return proxyRequest(request, {
    upstreamOrigin: API_INTERNAL_ORIGIN,
    upstreamPath,
    // api-patterns finding 16: allauth's two error shapes
    // ({status,errors} and {status,data:{flows}}) get re-emitted as
    // Keel's own {error:{code,message,details}} here, server-side, so the
    // browser sees exactly one error contract regardless of which half of
    // the API answered — reusing the same normalizer @keel/api-client
    // already ships and tests, rather than a second copy of this logic.
    transformErrorBody: (status, body) => normalizeErrorEnvelope(status, body),
  });
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
