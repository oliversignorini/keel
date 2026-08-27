/**
 * Content-Security-Policy for the app (docs/plans/phase-8.md 8.6;
 * narrowed by docs/adr/0002-auth-bff-shape.md). Every programmatic
 * `fetch()`/`XMLHttpRequest` this app makes is now same-origin — the
 * Next.js BFF proxies `/api/v1/…` and `/_allauth/…` to Django itself —
 * so `connect-src 'self'` (plus Sentry/PostHog) is now sufficient; it no
 * longer needs the API/stream origins the way it did pre-phase-11.
 *
 * `GoogleContinueLink`'s real `<form method="post">` is now also a
 * same-origin relative action, proxied by the BFF like everything else
 * (ADR 0002) — there is no longer any cross-origin call the browser
 * makes on its own, so both `connect-src` and the `form-action` this
 * revision adds can stay `'self'`-only.
 *
 * Pure function of env values so it's testable without a running Next
 * server — see csp.test.ts.
 */

function originOf(url: string | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

export interface CspEnv {
  sentryDsn?: string;
  posthogHost?: string;
  /** true under `next dev`. Next's dev server evaluates its hot-reload
   * bundle via `eval()` (webpack/React Refresh) — without 'unsafe-eval'
   * here, the CSP blocks that eval and the app never hydrates at all in
   * dev (confirmed live: without this, every page hangs on "Loading…"
   * with a CSP violation in the console, not a visible error). The
   * production build needs no eval and gets none. */
  dev?: boolean;
}

export function buildContentSecurityPolicy(env: CspEnv): string {
  const connectSrc = new Set<string>(["'self'"]);
  const posthogOrigin = originOf(env.posthogHost);
  if (posthogOrigin) connectSrc.add(posthogOrigin);
  const sentryOrigin = originOf(env.sentryDsn);
  if (sentryOrigin) connectSrc.add(sentryOrigin);

  const scriptSrc = ["'self'", "'unsafe-inline'"];
  if (env.dev) scriptSrc.push("'unsafe-eval'");

  const directives = [
    "default-src 'self'",
    // Next.js ships an inline bootstrap script with the initial page
    // payload — 'unsafe-inline' here (not a nonce) is the pragmatic
    // default the same way Next's own docs describe for the App
    // Router without per-request nonce middleware.
    `script-src ${scriptSrc.join(" ")}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https:",
    "font-src 'self' data:",
    `connect-src ${[...connectSrc].join(" ")}`,
    "form-action 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
  ];
  return directives.join("; ");
}
