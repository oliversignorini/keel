import { describe, expect, it } from "vitest";

import { buildContentSecurityPolicy } from "./csp";

describe("buildContentSecurityPolicy", () => {
  it("always allows 'self' in connect-src", () => {
    const csp = buildContentSecurityPolicy({});

    expect(csp).toContain("connect-src 'self'");
  });

  it("allows the API origin — the criterion that fails in production only", () => {
    const csp = buildContentSecurityPolicy({ apiBaseUrl: "https://api.acme.com" });

    expect(csp).toContain("connect-src 'self' https://api.acme.com");
  });

  it("allows the SSE stream origin alongside the API origin", () => {
    const csp = buildContentSecurityPolicy({
      apiBaseUrl: "https://api.acme.com",
      apiStreamUrl: "https://api.acme.com/stream",
    });

    const connectSrc = csp.match(/connect-src ([^;]+)/)?.[1] ?? "";
    expect(connectSrc.split(" ")).toEqual(["'self'", "https://api.acme.com"]);
  });

  it("de-duplicates when the API and stream share an origin", () => {
    const csp = buildContentSecurityPolicy({
      apiBaseUrl: "https://api.acme.com",
      apiStreamUrl: "https://api.acme.com:8001",
    });

    const connectSrc = csp.match(/connect-src ([^;]+)/)?.[1] ?? "";
    expect(connectSrc.split(" ")).toEqual([
      "'self'",
      "https://api.acme.com",
      "https://api.acme.com:8001",
    ]);
  });

  it("allows the Sentry ingest origin when a DSN is configured", () => {
    const csp = buildContentSecurityPolicy({
      sentryDsn: "https://abc123@o12345.ingest.sentry.io/67890",
    });

    expect(csp).toContain("https://o12345.ingest.sentry.io");
  });

  it("allows the PostHog host when configured", () => {
    const csp = buildContentSecurityPolicy({ posthogHost: "https://us.i.posthog.com" });

    expect(csp).toContain("https://us.i.posthog.com");
  });

  it("ignores a blank or malformed URL rather than throwing", () => {
    expect(() => buildContentSecurityPolicy({ apiBaseUrl: "" })).not.toThrow();
    expect(() => buildContentSecurityPolicy({ apiBaseUrl: "not a url" })).not.toThrow();
  });

  it("allows 'unsafe-eval' only in dev — Next's HMR needs eval(), production doesn't", () => {
    const devCsp = buildContentSecurityPolicy({ dev: true });
    const prodCsp = buildContentSecurityPolicy({ dev: false });

    expect(devCsp).toContain("'unsafe-eval'");
    expect(prodCsp).not.toContain("'unsafe-eval'");
  });

  it("denies framing entirely", () => {
    const csp = buildContentSecurityPolicy({});

    expect(csp).toContain("frame-ancestors 'none'");
  });
});
