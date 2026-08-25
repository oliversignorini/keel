import { describe, expect, it } from "vitest";

import { postFrontmatterSchema } from "./post-schema";

const VALID = {
  title: "A post",
  description: "A description",
  date: "2026-01-15",
  author: "Keel team",
  content: "Body",
};

describe("postFrontmatterSchema", () => {
  it("accepts well-formed frontmatter", () => {
    expect(postFrontmatterSchema.safeParse(VALID).success).toBe(true);
  });

  it("rejects a post missing a required field", () => {
    const withoutDate: Partial<typeof VALID> = { ...VALID };
    delete withoutDate.date;
    expect(postFrontmatterSchema.safeParse(withoutDate).success).toBe(false);
  });

  it("rejects a non-ISO date", () => {
    const result = postFrontmatterSchema.safeParse({ ...VALID, date: "15 Jan 2026" });
    expect(result.success).toBe(false);
  });
});
