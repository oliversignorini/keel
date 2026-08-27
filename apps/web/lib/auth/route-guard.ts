/**
 * Django's default session cookie name. Confirm against
 * docs/auth-client-contract.md once p2-auth-api lands it.
 */
export const SESSION_COOKIE_NAME = "sessionid";

const PROTECTED_PREFIXES = ["/app", "/account", "/onboarding"];

function matchesPrefix(pathname: string, prefixes: string[]): boolean {
  return prefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

/**
 * Pure decision function behind the Next.js middleware (middleware.ts).
 * `hasSession` is only "a session cookie is present" — this can never be
 * "the session is valid or still authorized". That check happens on the
 * API for every request; this function exists purely to avoid flashing a
 * protected page at a visitor with no cookie at all.
 *
 * Phase 11 (docs/adr/0002-auth-bff-shape.md): this used to also redirect
 * a visitor with a session cookie *away* from `/login`/`/signup`, as a
 * "don't show the auth forms to someone plainly already logged in"
 * convenience. That heuristic is unsound in exactly the way its own
 * docstring warned about: allauth sets a real `sessionid` cookie for a
 * *pending*, not-yet-authenticated flow too (email verification pending,
 * MFA pending) — a user who signed up but hasn't verified yet has a
 * session cookie and is not logged in. Confirmed live: such a visitor
 * hitting `/login` was bounced to the app host's root, which immediately
 * 401s against `GET /api/v1/me/` and bounces back to `/login` via
 * `useMe`'s own redirect (lib/org/use-me.ts) — an unrecoverable loop with
 * no way to ever reach the login form again. Showing the login form to a
 * genuinely-already-authenticated visitor is a harmless flash by
 * comparison, so the asymmetry is deliberate: protect the pages that
 * need real content, never gate the one page whose entire job is letting
 * someone in.
 */
export function resolveGuardRedirect(pathname: string, hasSession: boolean): string | null {
  if (matchesPrefix(pathname, PROTECTED_PREFIXES) && !hasSession) {
    return `/login?next=${encodeURIComponent(pathname)}`;
  }

  return null;
}
