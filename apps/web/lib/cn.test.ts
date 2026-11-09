import { describe, expect, it } from "vitest";

import { cn } from "./cn";

describe("cn", () => {
  it("joins truthy values with a space", () => {
    expect(cn("flex", "grid", "block")).toBe("flex grid block");
  });

  it("drops falsy values", () => {
    expect(cn("flex", false, null, undefined, "grid")).toBe("flex grid");
  });

  it("returns an empty string when nothing survives", () => {
    expect(cn(false, undefined)).toBe("");
  });
});
