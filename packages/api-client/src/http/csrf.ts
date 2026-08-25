const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

/**
 * Django's default CSRF cookie name. Confirm against docs/auth-client-contract.md
 * once the p2-auth-api worktree lands it — CSRF_COOKIE_NAME is a one-line
 * settings change that would move this.
 */
export const CSRF_COOKIE_NAME = "csrftoken";
export const CSRF_HEADER_NAME = "X-CSRFToken";

export function isUnsafeMethod(method: string): boolean {
  return !SAFE_METHODS.has(method.toUpperCase());
}

export function readCsrfCookie(): string | undefined {
  if (typeof document === "undefined") {
    return undefined;
  }

  for (const pair of document.cookie.split(";")) {
    const [rawName, ...rawValue] = pair.trim().split("=");
    if (rawName === CSRF_COOKIE_NAME) {
      return decodeURIComponent(rawValue.join("="));
    }
  }

  return undefined;
}
