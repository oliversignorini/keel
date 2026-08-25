import { toAppHost } from "@/lib/host";

/**
 * Where an authenticated visitor with no explicit `next` should land —
 * the app host's root ("/", which the middleware rewrites internally to
 * /app). Client components read `next` from the URL themselves, so this
 * has to compute the app host from the browser's own location rather
 * than an env var: it must work in dev (lvh.me), in a real deployment
 * (acme.com), and in a test/CI environment (localhost) alike.
 */
export function defaultAppUrl(): string {
  if (typeof window === "undefined") return "/app";
  return `${window.location.protocol}//${toAppHost(window.location.host)}/`;
}

/**
 * Navigates to `target`, which may be same-host relative path (the
 * common case) or an absolute cross-host URL (plan 6.A: `next` crosses
 * from the apex login page to the app host, or vice versa). Next's
 * client-side router can only navigate within its own origin, so a
 * cross-origin target needs a real navigation instead.
 */
export function navigateTo(router: { push: (href: string) => void }, target: string): void {
  if (typeof window !== "undefined" && /^https?:\/\//.test(target)) {
    const targetOrigin = new URL(target).origin;
    if (targetOrigin !== window.location.origin) {
      window.location.href = target;
      return;
    }
  }
  router.push(target);
}
