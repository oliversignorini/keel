/**
 * Host-based routing helpers (plan 6.A): the app shell lives on its own
 * subdomain (`app.acme.com` / `app.lvh.me` in dev), split from the
 * (marketing) and (auth) routes on the apex. Pure string functions —
 * used by both middleware.ts (server, Host header) and client components
 * that need to build a cross-host link (window.location.host).
 *
 * `host` here always means "hostname, optionally with :port" — the shape
 * both `NextURL.host` and `window.location.host` already return — so
 * these never need to special-case a port.
 */

function label(host: string): string {
  return host.split(":")[0]?.split(".")[0] ?? "";
}

export function isAppHost(host: string): boolean {
  return label(host) === "app";
}

export function toApexHost(host: string): string {
  return host.startsWith("app.") ? host.slice(4) : host;
}

export function toAppHost(host: string): string {
  return host.startsWith("app.") ? host : `app.${host}`;
}
