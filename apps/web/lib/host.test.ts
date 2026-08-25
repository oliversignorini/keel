import { describe, expect, it } from "vitest";

import { isAppHost, toApexHost, toAppHost } from "./host";

describe("isAppHost", () => {
  it("is true for the app subdomain, with or without a port", () => {
    expect(isAppHost("app.lvh.me")).toBe(true);
    expect(isAppHost("app.lvh.me:3000")).toBe(true);
    expect(isAppHost("app.acme.com")).toBe(true);
  });

  it("is false for the apex or any other subdomain", () => {
    expect(isAppHost("lvh.me:3000")).toBe(false);
    expect(isAppHost("acme.com")).toBe(false);
    expect(isAppHost("api.lvh.me:8000")).toBe(false);
    expect(isAppHost("localhost:3000")).toBe(false);
  });
});

describe("toApexHost", () => {
  it("strips a leading app. label", () => {
    expect(toApexHost("app.lvh.me:3000")).toBe("lvh.me:3000");
    expect(toApexHost("app.acme.com")).toBe("acme.com");
  });

  it("is a no-op when already the apex", () => {
    expect(toApexHost("lvh.me:3000")).toBe("lvh.me:3000");
  });
});

describe("toAppHost", () => {
  it("adds the app. label", () => {
    expect(toAppHost("lvh.me:3000")).toBe("app.lvh.me:3000");
    expect(toAppHost("acme.com")).toBe("app.acme.com");
  });

  it("is a no-op when already the app host", () => {
    expect(toAppHost("app.lvh.me:3000")).toBe("app.lvh.me:3000");
  });
});
