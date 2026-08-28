import { describe, expect, it } from "vitest";

import { namesFor } from "../naming.js";
import { DEFAULT_DISPLAY_FIELD, renderSpec } from "./e2e.js";

describe("renderSpec", () => {
  it("names the file's test.describe block and API path after the resource", () => {
    const source = renderSpec(namesFor("Invoice"), DEFAULT_DISPLAY_FIELD);
    expect(source).toContain('test.describe("Invoice — CRUD"');
    expect(source).toContain("/app/${orgSlug}/invoices");
    expect(source).toContain("/api/v1/orgs/${orgSlug}/invoices/");
  });

  it("fills and asserts on the display field's label", () => {
    const source = renderSpec(namesFor("Invoice"), {
      name: "number",
      kind: "str",
      optional: false,
    });
    expect(source).toContain('getByLabel(new RegExp("number"');
  });

  it("skips itself until E2E_ORG_SLUG is provided", () => {
    const source = renderSpec(namesFor("Invoice"), DEFAULT_DISPLAY_FIELD);
    expect(source).toContain("test.skip(!orgSlug");
  });
});
