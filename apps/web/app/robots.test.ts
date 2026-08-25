import { describe, expect, it } from "vitest";

import robots from "./robots";

describe("robots", () => {
  it("disallows the authenticated app and account surfaces", () => {
    const { rules } = robots();
    const disallow = Array.isArray(rules) ? rules[0]?.disallow : rules.disallow;
    expect(disallow).toEqual(expect.arrayContaining(["/app/", "/account/"]));
  });

  it("points at the sitemap", () => {
    expect(robots().sitemap).toContain("/sitemap.xml");
  });
});
