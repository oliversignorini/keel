import { describe, expect, it } from "vitest";

import sitemap from "./sitemap";

describe("sitemap", () => {
  it("includes marketing and blog routes", () => {
    const urls = sitemap().map((entry) => entry.url);

    expect(urls).toEqual(
      expect.arrayContaining([
        expect.stringMatching(/\/$/),
        expect.stringContaining("/pricing"),
        expect.stringContaining("/blog"),
        expect.stringContaining("/legal/terms"),
        expect.stringContaining("/legal/privacy"),
      ]),
    );
  });

  it("excludes /app/* routes", () => {
    const urls = sitemap().map((entry) => entry.url);
    expect(urls.some((url) => url.includes("/app/"))).toBe(false);
  });

  it("includes one entry per blog post", () => {
    const urls = sitemap().map((entry) => entry.url);
    const postUrls = urls.filter((url) => /\/blog\/.+/.test(url));
    expect(postUrls.length).toBeGreaterThanOrEqual(3);
  });
});
