import { describe, expect, it } from "vitest";

import { InvalidResourceName, namesFor, pluralize } from "./naming.js";

describe("pluralize", () => {
  it("handles the three cases the codebase actually produces", () => {
    expect(pluralize("widget")).toBe("widgets");
    expect(pluralize("invoice")).toBe("invoices");
    expect(pluralize("category")).toBe("categories");
    expect(pluralize("address")).toBe("addresses");
    expect(pluralize("box")).toBe("boxes");
    // A vowel before the y is not the -ies case.
    expect(pluralize("survey")).toBe("surveys");
  });
});

describe("namesFor", () => {
  it("derives every token from a single-word name", () => {
    expect(namesFor("Widget")).toEqual({
      Resource: "Widget",
      resource: "widget",
      resources: "widgets",
      Resources: "Widgets",
      RESOURCE: "WIDGET",
      RESOURCES: "WIDGETS",
      app: "widgets",
    });
  });

  it("splits a multi-word PascalCase name into snake_case", () => {
    expect(namesFor("InvoiceLine")).toEqual({
      Resource: "InvoiceLine",
      resource: "invoice_line",
      resources: "invoice_lines",
      Resources: "InvoiceLines",
      RESOURCE: "INVOICE_LINE",
      RESOURCES: "INVOICE_LINES",
      app: "invoice_lines",
    });
  });

  it("rejects anything that is not PascalCase singular", () => {
    for (const bad of ["widget", "invoice_line", "Invoice-Line", "", "3Widgets"]) {
      expect(() => namesFor(bad)).toThrow(InvalidResourceName);
    }
  });
});
