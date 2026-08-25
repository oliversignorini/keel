/**
 * Django's default session cookie name. Confirm against
 * docs/auth-client-contract.md once p2-auth-api lands it.
 */
export const SESSION_COOKIE_NAME = "sessionid";

const PROTECTED_PREFIXES = ["/app", "/account", "/onboarding"];
const AUTH_ONLY_PATHS = ["/login", "/signup"];

function matchesPrefix(pathname: string, prefixes: string[]): boolean {
  return prefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

/**
 * Pure decision function behind the Next.js middleware (middleware.ts).
 * `hasSession` is only "a session cookie is present" — this can never be
 * "the session is valid or still authorized". That check happens on the
 * API for every request; this function exists purely to avoid flashing a
 * protected page at a visitor with no cookie at all, or the auth forms at
 * one who plainly already has a session.
 */
export function resolveGuardRedirect(pathname: string, hasSession: boolean): string | null {
  if (matchesPrefix(pathname, PROTECTED_PREFIXES) && !hasSession) {
    return `/login?next=${encodeURIComponent(pathname)}`;
  }

  if (matchesPrefix(pathname, AUTH_ONLY_PATHS) && hasSession) {
    return "/app";
  }

  return null;
}
