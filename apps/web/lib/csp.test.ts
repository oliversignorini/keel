import { describe, expect, it } from "vitest";

import { buildContentSecurityPolicy } from "./csp";

describe("buildContentSecurityPolicy", () => {
  it("always allows 'self' in connect-src", () => {
    const csp = buildContentSecurityPolicy({});

    expect(csp).toContain("connect-src 'self'");
  });

  it("does not allow any API/stream origin in connect-src — every fetch is same-origin via the BFF proxy (ADR 0002)", () => {
    const csp = buildContentSecurityPolicy({});

    const connectSrc = csp.match(/connect-src ([^;]+)/)?.[1] ?? "";
    expect(connectSrc.split(" ")).toEqual(["'self'"]);
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

  it("scopes form-action to 'self' — GoogleContinueLink's <form> post is now same-origin too (ADR 0002)", () => {
    const csp = buildContentSecurityPolicy({});

    expect(csp).toContain("form-action 'self'");
  });

  it("ignores a blank or malformed Sentry DSN rather than throwing", () => {
    expect(() => buildContentSecurityPolicy({ sentryDsn: "" })).not.toThrow();
    expect(() => buildContentSecurityPolicy({ sentryDsn: "not a url" })).not.toThrow();
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
