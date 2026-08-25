import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE_NAME, resolveGuardRedirect } from "./lib/auth/route-guard";

// This middleware is a redirect convenience, not the enforcement point —
// the API is (keel-prd.md §4 "Auth architecture"). It only checks whether
// a session cookie is present, never whether that session is still valid,
// because the cookie is HttpOnly and its validity can only be decided by
// Django. A visitor who clears cookies mid-session, or whose session
// expired server-side, still passes this check and must get a real 401
// from the API — every page under /app and /account has to handle that
// itself rather than assuming middleware already enforced access.
export function middleware(request: NextRequest) {
  const hasSession = request.cookies.has(SESSION_COOKIE_NAME);
  const redirectTo = resolveGuardRedirect(request.nextUrl.pathname, hasSession);

  if (redirectTo) {
    return NextResponse.redirect(new URL(redirectTo, request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/app/:path*", "/account/:path*", "/login", "/signup"],
};
