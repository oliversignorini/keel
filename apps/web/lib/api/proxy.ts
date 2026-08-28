import type { NextRequest } from "next/server";

/**
 * The BFF proxy (docs/adr/0002-auth-bff-shape.md): every `/api/v1/…` and
 * `/_allauth/…` call the browser makes is same-origin against this Next.js
 * server, which forwards it to Django's real origin itself. The browser
 * never holds Django's address; `identityFetch` (packages/api-client/src/
 * http/mutator.ts) calls these relative paths directly.
 *
 * This is one shared function rather than one handler per endpoint (the
 * phase's own instruction: "a single typed proxy path, not one handler per
 * endpoint") — apps/web/app/api/v1/[...path]/route.ts and apps/web/app/api/
 * internal/allauth/[...path]/route.ts are both thin wrappers around it.
 */

/** Request/response headers that describe *this specific hop*, not the
 * payload — copying them through to the other side of the proxy would be
 * wrong (a stale Content-Length after body rewriting, a Host header that
 * names the wrong server) or meaningless (hop-by-hop headers, RFC 7230
 * §6.1, that never survive an intermediary by definition). */
const HOP_BY_HOP_REQUEST_HEADERS = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "host",
  "content-length",
]);

/** Headers that describe *who the client is and how they connected*, which
 * only a trusted proxy may assert. This proxy sits between the public
 * internet and Django, so anything the browser sent under these names is
 * a claim, not a fact: Django's anon rate limiting keys its bucket off
 * `X-Forwarded-For` when configured to trust proxies
 * (apps/api/keel/core/throttle.py) and its `SECURE_PROXY_SSL_HEADER`
 * trusts `X-Forwarded-Proto` (apps/api/config/settings/prod.py), so a
 * browser that sets either per request would otherwise mint itself a
 * fresh rate-limit bucket every call and tell Django an http:// request
 * arrived over https://. Deleted rather than rewritten — the platform's
 * own edge and this hop's fetch set the real values on the way out. */
const CLIENT_ASSERTED_FORWARDING_HEADERS = new Set([
  "x-forwarded-for",
  "x-forwarded-proto",
  "x-forwarded-host",
  "x-forwarded-port",
  "x-real-ip",
  "forwarded",
]);

const HOP_BY_HOP_RESPONSE_HEADERS = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "content-encoding", // undici already decoded the body; a stale encoding header would corrupt it
  "content-length", // body may be rewritten (error-envelope translation) — let the runtime recompute it
]);

export interface ProxyOptions {
  /** e.g. `http://api.lvh.me:8000` — server-only, never read by the browser. */
  upstreamOrigin: string;
  /** The path (with query string already applied by the caller) on
   * `upstreamOrigin` this request maps to, e.g. `/api/v1/orgs/acme/widgets/`. */
  upstreamPath: string;
  /** When given, every non-2xx JSON response body is replaced with this
   * function's return value before reaching the browser — the allauth
   * route uses it to re-emit Keel's own error envelope (api-patterns
   * finding 16); the `/api/v1` route omits it (already Keel-shaped). */
  transformErrorBody?: (status: number, body: unknown) => unknown;
}

export async function proxyRequest(request: NextRequest, options: ProxyOptions): Promise<Response> {
  const upstreamUrl = new URL(options.upstreamPath, options.upstreamOrigin);
  upstreamUrl.search = request.nextUrl.search;

  const requestHeaders = new Headers(request.headers);
  for (const name of HOP_BY_HOP_REQUEST_HEADERS) {
    requestHeaders.delete(name);
  }
  for (const name of CLIENT_ASSERTED_FORWARDING_HEADERS) {
    requestHeaders.delete(name);
  }

  const hasBody = !["GET", "HEAD"].includes(request.method);
  const init: RequestInit = {
    method: request.method,
    headers: requestHeaders,
    redirect: "manual",
    signal: request.signal,
  };
  if (hasBody) {
    // Buffered, not streamed: every request body this proxy ever forwards
    // is a small JSON or form-urlencoded payload — presigned uploads PUT
    // straight to storage and never touch this proxy (docs/adr/0002-auth-bff-shape.md).
    // Two things went wrong before landing on `.blob()`, both confirmed
    // live against the dev stack: `body: request.body, duplex: 'half'`
    // (a real stream) drops Content-Length and forces chunked transfer
    // encoding, which Django's dev server (wsgiref, via `manage.py
    // runserver`) does not decode — the upstream request arrived with an
    // empty body, surfacing as allauth's "This field is required" on
    // every field. `request.arrayBuffer()` avoids that but throws
    // `Cannot perform ArrayBuffer.prototype.slice on a detached
    // ArrayBuffer` from inside `fetch` when the incoming request already
    // passed through the middleware rewrite (docs/adr/0002-auth-bff-shape.md's
    // `/_allauth/…` rewrite) — Next.js's rewrite machinery appears to
    // already hold/transfer that buffer. `.blob()` sidesteps both.
    init.body = await request.blob();
  }

  const upstreamResponse = await fetch(upstreamUrl, init);

  const responseHeaders = new Headers(upstreamResponse.headers);
  for (const name of HOP_BY_HOP_RESPONSE_HEADERS) {
    responseHeaders.delete(name);
  }
  // Headers.set()/append() on a Response can only carry one `set-cookie`
  // value structurally — Django frequently sets two in one response
  // (sessionid + csrftoken) — so these are re-added individually below via
  // getSetCookie() rather than left in the copied Headers object above.
  responseHeaders.delete("set-cookie");

  let responseBody: BodyInit | null = upstreamResponse.body;
  const contentType = upstreamResponse.headers.get("content-type") ?? "";
  if (
    options.transformErrorBody &&
    !upstreamResponse.ok &&
    contentType.includes("application/json")
  ) {
    const rawText = await upstreamResponse.text();
    const parsedBody = rawText ? safeJsonParse(rawText) : null;
    responseBody = JSON.stringify({
      error: options.transformErrorBody(upstreamResponse.status, parsedBody),
    });
    responseHeaders.set("content-type", "application/json");
  }

  const response = new Response(responseBody, {
    status: upstreamResponse.status,
    statusText: upstreamResponse.statusText,
    headers: responseHeaders,
  });

  for (const cookie of upstreamResponse.headers.getSetCookie()) {
    response.headers.append("set-cookie", cookie);
  }

  return response;
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}
