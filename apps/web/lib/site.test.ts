import { afterEach, describe, expect, it, vi } from "vitest";

describe("SITE_URL", () => {
  const original = process.env.NEXT_PUBLIC_SITE_URL;

  afterEach(() => {
    if (original === undefined) delete process.env.NEXT_PUBLIC_SITE_URL;
    else process.env.NEXT_PUBLIC_SITE_URL = original;
    vi.resetModules();
  });

  it("defaults to localhost when unset", async () => {
    delete process.env.NEXT_PUBLIC_SITE_URL;
    const { SITE_URL } = await import("./site");
    expect(SITE_URL).toBe("http://localhost:3000");
  });

  it("strips a trailing slash from a configured origin", async () => {
    process.env.NEXT_PUBLIC_SITE_URL = "https://acme.com/";
    const { SITE_URL } = await import("./site");
    expect(SITE_URL).toBe("https://acme.com");
  });
});
