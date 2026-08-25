import { describe, expect, it, vi } from "vitest";

let mockHost = "lvh.me:3000";
vi.mock("next/headers", () => ({
  headers: async () => new Map([["host", mockHost]]),
}));

const { default: robots } = await import("./robots");

describe("robots", () => {
  it("disallows the authenticated app and account surfaces on the apex", async () => {
    mockHost = "lvh.me:3000";
    const { rules } = await robots();
    const disallow = Array.isArray(rules) ? rules[0]?.disallow : rules.disallow;
    expect(disallow).toEqual(expect.arrayContaining(["/app/", "/account/"]));
  });

  it("disallows everything on the app host — plan 6.A: it's all authenticated", async () => {
    mockHost = "app.lvh.me:3000";
    const { rules } = await robots();
    const disallow = Array.isArray(rules) ? rules[0]?.disallow : rules.disallow;
    expect(disallow).toBe("/");
  });

  it("points at the sitemap on both hosts", async () => {
    mockHost = "lvh.me:3000";
    expect((await robots()).sitemap).toContain("/sitemap.xml");
    mockHost = "app.lvh.me:3000";
    expect((await robots()).sitemap).toContain("/sitemap.xml");
  });
});
