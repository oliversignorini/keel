import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE_NAME, resolveGuardRedirect } from "./lib/auth/route-guard";
import { isAppHost, toApexHost, toAppHost } from "./lib/host";

// This middleware is a redirect convenience, not the enforcement point —
// the API is. It only checks whether
// a session cookie is present, never whether that session is still valid,
// because the cookie is HttpOnly and its validity can only be decided by
// Django. A visitor who clears cookies mid-session, or whose session
// expired server-side, still passes this check and must get a real 401
// from the API — every page under /app and /account has to handle that
// itself rather than assuming middleware already enforced access.
//
// Plan 6.A layers host-based routing on top: `app.*` serves the (app)
// route group, the apex serves (marketing) and (auth). The file layout
// under app/(app)/app/[org]/... doesn't change — only the app host's
// *visible* URLs drop the /app segment, via an internal rewrite. Because
// (auth) only exists on the apex, a redirect this middleware issues
// between the two hosts must be an absolute URL, or the browser just
// requests a path that doesn't exist on its current host.
export function middleware(request: NextRequest) {
  // request.nextUrl.host can't be trusted here — Next.js derives it from
  // the dev server's own bind address in some setups rather than the
  // incoming request, which would make every host-based decision below
  // silently see "localhost" no matter what the browser actually asked
  // for. The `Host` header is what the browser and every proxy in front
  // of this actually sent.
  const host = request.headers.get("host") ?? request.nextUrl.host;
  const pathname = request.nextUrl.pathname;
  const onAppHost = isAppHost(host);
  const hasSession = request.cookies.has(SESSION_COOKIE_NAME);

  // docs/adr/0002-auth-bff-shape.md: `/_allauth/…` must stay the literal
  // wire path (it's baked into every generated allauth client function),
  // but Next.js treats a real `app/_allauth` folder as an unrouted
  // "private folder" — so the actual handler lives at the routable
  // `/api/internal/allauth/…` and this rewrite is what keeps the two in
  // sync. This has to be a middleware rewrite rather than a
  // `next.config.ts` `rewrites()` entry: `withContentCollections` (see
  // that file) drops a `rewrites` key from the config object entirely,
  // so one declared there is silently never called.
  if (pathname === "/_allauth" || pathname.startsWith("/_allauth/")) {
    const target = request.nextUrl.clone();
    target.pathname = `/api/internal/allauth${pathname.slice("/_allauth".length)}`;
    return NextResponse.rewrite(target);
  }

  // A stray /app/* request on the apex (the pre-6.A URL shape, or a stale
  // bookmark) is sent to its new home on the app host rather than served
  // twice from two hosts.
  if (!onAppHost && (pathname === "/app" || pathname.startsWith("/app/"))) {
    const target = request.nextUrl.clone();
    target.host = toAppHost(host);
    target.pathname = pathname.slice("/app".length) || "/";
    return NextResponse.redirect(target);
  }

  // /account isn't part of the (app) route group's file layout (it has no
  // /app prefix to begin with), so it needs no rewrite on either host.
  const internalPathname =
    onAppHost && !pathname.startsWith("/account")
      ? pathname === "/"
        ? "/app"
        : `/app${pathname}`
      : pathname;

  const redirectTo = resolveGuardRedirect(internalPathname, hasSession);

  if (redirectTo?.startsWith("/login")) {
    // Unauthenticated on a protected path: login only exists on the
    // apex, and `next` must be able to send the browser back across
    // hosts, so it's the full current URL whenever the request came in
    // on the app host.
    const next = onAppHost
      ? `${request.nextUrl.protocol}//${host}${pathname}${request.nextUrl.search}`
      : `${pathname}${request.nextUrl.search}`;
    const target = request.nextUrl.clone();
    target.host = toApexHost(host);
    target.pathname = "/login";
    target.search = `?next=${encodeURIComponent(next)}`;
    return NextResponse.redirect(target);
  }

  if (internalPathname !== pathname) {
    const target = request.nextUrl.clone();
    target.pathname = internalPathname;
    return NextResponse.rewrite(target);
  }

  return NextResponse.next();
}

export const config = {
  // Widened from the pre-6.A matcher (which only listed known protected
  // paths) because every app-host request now needs the /app rewrite,
  // not only the ones route-guard cares about.
  matcher: ["/((?!_next/|favicon.ico|api/).*)"],
};
