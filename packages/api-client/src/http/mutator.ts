import { errorFromStatus } from "./errors";
import { normalizeErrorEnvelope } from "./normalize-envelope";
import { CSRF_HEADER_NAME, isUnsafeMethod, readCsrfCookie } from "./csrf";

/**
 * Django API origin. Same-origin in prod (api.<domain> behind the app's
 * registrable domain, per keel-prd.md §4 "Auth architecture") but distinct
 * in dev, so it is always explicit rather than relying on a relative URL.
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/**
 * The orval fetch-client mutator. Every generated request function in
 * src/generated calls through here with a generic parameter shaped like
 * `{ data, status, headers }` (orval's fetch-client response union) — but
 * we deliberately never return the error-shaped members of that union.
 * Any non-2xx response throws a typed ApiError (./errors.ts) instead, so
 * callers use try/catch + `instanceof`, not `.status` narrowing. That is
 * what B.1 asks for: 401/402/403/404/409/422/429 as distinct types the
 * caller cannot accidentally treat alike.
 */
export async function identityFetch<T>(url: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);

  if (isUnsafeMethod(method)) {
    const csrfToken = readCsrfCookie();
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

  return { data: body, status: response.status, headers: response.headers } as T;
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
