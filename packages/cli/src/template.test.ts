import { describe, expect, it } from "vitest";

import { namesFor } from "./naming.js";
import { render, substituteTokens, TemplateError } from "./template.js";

const names = namesFor("Widget");
const ctx = (flags: string[] = [], inserts: Record<string, string[]> = {}) => ({
  names,
  flags: new Set(flags),
  inserts,
});

describe("substituteTokens", () => {
  it("prefers the longer token so __Resources__ is never read as __Resource__ + s", () => {
    expect(substituteTokens("__Resources__", names)).toBe("Widgets");
    expect(substituteTokens("__resources__", names)).toBe("widgets");
    expect(substituteTokens("__RESOURCES__", names)).toBe("WIDGETS");
    expect(substituteTokens("__Resource__", names)).toBe("Widget");
    expect(substituteTokens("__RESOURCE__", names)).toBe("WIDGET");
  });

  it("substitutes the UPPER_SNAKE tokens a Perm constant needs", () => {
    expect(substituteTokens("Perm.__RESOURCE___VIEW", names)).toBe("Perm.WIDGET_VIEW");
    expect(substituteTokens("Perm.__RESOURCES___MANAGE", names)).toBe("Perm.WIDGETS_MANAGE");
  });

  it("substitutes a token that is a prefix of a longer identifier", () => {
    expect(substituteTokens("__resources___created", names)).toBe("widgets_created");
    expect(substituteTokens("__Resource__Resource", names)).toBe("WidgetResource");
    expect(substituteTokens("list___resources__", names)).toBe("list_widgets");
  });
});

describe("keel:if", () => {
  it("keeps a region whose flag is on and drops one whose flag is off", () => {
    const source = ["a", "# keel:if fk", "b", "# keel:endif", "c"].join("\n");
    expect(render(source, ctx(["fk"]), "t")).toBe("a\nb\nc");
    expect(render(source, ctx([]), "t")).toBe("a\nc");
  });

  it("nests, and drops an inner region inside a dropped outer one", () => {
    const source = [
      "# keel:if outer",
      "o",
      "# keel:if inner",
      "i",
      "# keel:endif",
      "# keel:endif",
    ].join("\n");
    expect(render(source, ctx(["outer", "inner"]), "t")).toBe("o\ni");
    expect(render(source, ctx(["outer"]), "t")).toBe("o");
    expect(render(source, ctx(["inner"]), "t")).toBe("");
  });

  it("refuses an unbalanced region rather than guessing", () => {
    expect(() => render("# keel:if x\na", ctx(["x"]), "t")).toThrow(TemplateError);
    expect(() => render("# keel:endif", ctx(), "t")).toThrow(TemplateError);
  });
});

describe("keel:if — TypeScript and JSX comment syntax", () => {
  it("accepts `//` markers, for real .ts/.tsx template files", () => {
    const source = ["a", "// keel:if fk", "b", "// keel:endif", "c"].join("\n");
    expect(render(source, ctx(["fk"]), "t")).toBe("a\nb\nc");
    expect(render(source, ctx([]), "t")).toBe("a\nc");
  });

  it("accepts `{/* ... */}` markers, for inside JSX children", () => {
    const source = ["a", "{/* keel:if fk */}", "b", "{/* keel:endif */}", "c"].join("\n");
    expect(render(source, ctx(["fk"]), "t")).toBe("a\nb\nc");
    expect(render(source, ctx([]), "t")).toBe("a\nc");
  });

  it("accepts `{/* keel:insert slot */}` inside JSX children", () => {
    const source = ["<div>", "  {/* keel:insert body */}", "</div>"].join("\n");
    expect(render(source, ctx([], { body: ["  <Child />"] }), "t")).toBe(
      "<div>\n  <Child />\n</div>",
    );
  });

  it("does not treat an ordinary comment as a marker", () => {
    expect(render("// just a comment", ctx(), "t")).toBe("// just a comment");
    expect(render("{/* just a comment */}", ctx(), "t")).toBe("{/* just a comment */}");
  });
});

describe("keel:insert", () => {
  it("replaces the marker line with the supplied block", () => {
    const source = ["def f():", "    # keel:insert body"].join("\n");
    expect(render(source, ctx([], { body: ["    return 1"] }), "t")).toBe("def f():\n    return 1");
  });

  it("emits nothing for an empty block, leaving no stray marker", () => {
    expect(render("a\n# keel:insert body\nb", ctx([], { body: [] }), "t")).toBe("a\nb");
  });

  it("does not re-scan inserted lines for markers", () => {
    const inserted = ["# keel:if never", "kept"];
    expect(render("# keel:insert body", ctx([], { body: inserted }), "t")).toBe(
      "# keel:if never\nkept",
    );
  });

  it("fails loudly on a slot the generator forgot to supply", () => {
    expect(() => render("# keel:insert missing", ctx(), "t")).toThrow(TemplateError);
  });

  it("ignores a slot inside a dropped region", () => {
    const source = ["# keel:if off", "# keel:insert missing", "# keel:endif", "a"].join("\n");
    expect(render(source, ctx([]), "t")).toBe("a");
  });
});

describe("blank-line collapsing", () => {
  it("collapses the 3+ blank runs a dropped region leaves behind to Python's two", () => {
    // Three blank lines survive the dropped region; ruff format would
    // remove the third, so the renderer does it first.
    const source = ["a", "", "# keel:if off", "x", "# keel:endif", "", "", "b"].join("\n");
    expect(render(source, ctx([]), "t").split("\n")).toEqual(["a", "", "", "b"]);
  });
});
