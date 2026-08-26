/**
 * Content-Security-Policy for the app (docs/plans/phase-8.md 8.6). The
 * one directive that matters most here is `connect-src`: the app is on
 * `app.<domain>` and the API is on `api.<domain>` (PRD §4 "Auth
 * architecture"), so a `connect-src` that only allows `'self'` blocks
 * every `fetch()` this app makes — and only in production, since dev's
 * same-origin proxy setups don't usually hit this. Getting it wrong here
 * is exactly the failure the brief calls out: "fails in production
 * only."
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
  apiBaseUrl?: string;
  apiStreamUrl?: string;
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
  for (const url of [env.apiBaseUrl, env.apiStreamUrl, env.posthogHost]) {
    const origin = originOf(url);
    if (origin) connectSrc.add(origin);
  }
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
    "frame-ancestors 'none'",
    "base-uri 'self'",
  ];
  return directives.join("; ");
}
