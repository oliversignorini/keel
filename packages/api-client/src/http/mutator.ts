import type { ErrorEnvelope } from "../generated/identity.query";
import { errorFromStatus } from "./errors";
import { normalizeErrorEnvelope } from "./normalize-envelope";
import { CSRF_HEADER_NAME, isUnsafeMethod, readCsrfCookie } from "./csrf";

/**
 * Every generated operation's response type is a union of its success
 * variant(s) and one member per declared error status (400/401/403/404/
 * 409/422/429 — `keel.core.authz`'s router-level default, added so
 * the OpenAPI document publishes the error envelope).
 * `identityFetch` below never actually returns one of those error
 * members — it throws instead — so this strips them from `T` structurally
 * rather than by name: any union member whose `data` is shaped like
 * `ErrorEnvelope` is excluded, leaving only the success member(s) a caller
 * actually receives.
 */
type SuccessOnly<T> = T extends { data: ErrorEnvelope } ? never : T;

/**
 * Always same-origin (docs/adr/0002-auth-bff-shape.md): every generated
 * call is proxied by the Next.js BFF itself
 * (apps/web/app/api/v1/[...path]/route.ts, apps/web/app/api/internal/
 * allauth/[...path]/route.ts), which is the only thing that needs to know
 * Django's real address — see apps/web/lib/api/internal-origins.ts. This
 * is deliberately not read from an env var any more: there is no
 * deployment shape where a browser `fetch()` through this client should
 * ever target anything other than its own origin.
 */
export const API_BASE_URL = "";

/**
 * The orval fetch-client mutator. Every generated request function in
 * src/generated calls through here with a generic parameter shaped like
 * `{ data, status, headers }` (orval's fetch-client response union) — but
 * we deliberately never return the error-shaped members of that union.
 * Any non-2xx response throws a typed ApiError (./errors.ts) instead, so
 * callers use try/catch + `instanceof`, not `.status` narrowing:
 * 401/402/403/404/409/422/429 become distinct types the caller cannot
 * accidentally treat alike.
 */
export async function identityFetch<T>(
  url: string,
  options: RequestInit = {},
): Promise<SuccessOnly<T>> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);

  if (isUnsafeMethod(method)) {
    const csrfToken = await ensureCsrfCookie();
    if (csrfToken) {
      headers.set(CSRF_HEADER_NAME, csrfToken);
    }
  }

  const response = await fetch(`${API_BASE_URL}${url}`, {
    ...options,
    method,
    headers,
    credentials: "include",
  });

  const body = await parseBody(response);

  if (!response.ok) {
    const retryAfterHeader = response.headers.get("Retry-After");
    const retryAfterSeconds = retryAfterHeader ? Number(retryAfterHeader) : undefined;
    throw errorFromStatus(
      response.status,
      normalizeErrorEnvelope(response.status, body),
      retryAfterSeconds,
    );
  }

  return { data: body, status: response.status, headers: response.headers } as SuccessOnly<T>;
}

/**
 * Narrows a generated call's result to its success member and returns
 * `.data` — every generated request function's own *declared* return type
 * is still the full success-or-error union (orval types each declared
 * error status), even though `identityFetch`
 * above never actually produces one of the error members at runtime.
 * Callers under `lib/*\/api.ts` use this instead of a bare `result.data`
 * so that narrowing is one shared, documented cast rather than a
 * `result.data as X` repeated at each call site.
 */
export function unwrapData<T extends { data: unknown }>(result: T): SuccessOnly<T>["data"] {
  return result.data as SuccessOnly<T>["data"];
}

/**
 * Django only sets the `csrftoken` cookie as a side effect of a request
 * that calls `get_token()` — nothing GETs anything before a visitor's
 * very first action, so the first unsafe request of a fresh browser
 * session (no prior page load on the API's own origin ever set it) has no
 * cookie to send and gets rejected with a 403 "CSRF cookie not set"
 * before it ever reaches application code. Confirmed against the live
 * server while building this client (packages/api-client's regeneration
 * — see orval.config.ts) — every unsafe call up to and including the
 * very first login/signup was failing on exactly this before this fix.
 * `/_allauth/browser/v1/config` is the lightest, always-public GET this
 * API serves, so it doubles as the priming request.
 */
async function ensureCsrfCookie(): Promise<string | undefined> {
  const existing = readCsrfCookie();
  if (existing) {
    return existing;
  }
  await fetch(`${API_BASE_URL}/_allauth/browser/v1/config`, { credentials: "include" });
  return readCsrfCookie();
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return undefined;
  }

  const text = await response.text();
  if (!text) {
    return undefined;
  }

  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}
