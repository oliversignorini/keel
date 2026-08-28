import { describe, expect, it } from "vitest";

import {
  InvalidFieldSpec,
  parseFields,
  renderCreateParams,
  renderModelFields,
  renderOutFields,
  splitFieldSpecs,
} from "./fields.js";

const names = { resources: "invoices" };

describe("splitFieldSpecs", () => {
  it("does not split inside a choice(...) argument list", () => {
    expect(splitFieldSpecs("a:str,b:choice(draft,sent,paid),c:int")).toEqual([
      "a:str",
      "b:choice(draft,sent,paid)",
      "c:int",
    ]);
  });
});

describe("parseFields", () => {
  it("parses every supported type", () => {
    const fields = parseFields(
      "a:str,b:str(32),c:text,d:int,e:decimal,f:bool,g:date,h:datetime," +
        "i:choice(draft,sent),j:fk(accounts.User)?",
    );
    expect(fields.map((f) => f.kind)).toEqual([
      "str",
      "str",
      "text",
      "int",
      "decimal",
      "bool",
      "date",
      "datetime",
      "choice",
      "fk",
    ]);
    expect(fields[0]!.maxLength).toBe(255);
    expect(fields[1]!.maxLength).toBe(32);
    expect(fields[8]!.choices).toEqual(["draft", "sent"]);
    expect(fields[9]!.target).toEqual({ app: "accounts", model: "User" });
  });

  it("reads a trailing ? as optional", () => {
    const [required, optional] = parseFields("a:str,b:text?");
    expect(required!.optional).toBe(false);
    expect(optional!.optional).toBe(true);
  });

  it("rejects the field names the base model and template already own", () => {
    for (const name of ["id", "organization", "created_by"]) {
      expect(() => parseFields(`${name}:str`)).toThrow(InvalidFieldSpec);
    }
  });

  it("rejects a type outside the DSL rather than passing it through", () => {
    expect(() => parseFields("a:json")).toThrow(InvalidFieldSpec);
    expect(() => parseFields("a:models.EmailField")).toThrow(InvalidFieldSpec);
  });

  it("rejects a malformed fk target", () => {
    expect(() => parseFields("a:fk(User)?")).toThrow(InvalidFieldSpec);
    expect(() => parseFields("a:fk(accounts.user)?")).toThrow(InvalidFieldSpec);
    expect(() => parseFields("a:fk()?")).toThrow(InvalidFieldSpec);
  });

  it("rejects a non-null fk, because the factory cannot invent a related row", () => {
    expect(() => parseFields("owner:fk(accounts.User)")).toThrow(InvalidFieldSpec);
  });

  it("returns nothing for an absent or empty spec", () => {
    expect(parseFields(undefined)).toEqual([]);
    expect(parseFields("  ")).toEqual([]);
  });
});

describe("renderModelFields", () => {
  it("renders the reference slice's own three fields exactly", () => {
    const rendered = renderModelFields(parseFields("name:str,description:text?,status:str(32)?"), {
      resources: "widgets",
    });
    expect(rendered).toEqual([
      "    name = models.CharField(max_length=255)",
      '    description = models.TextField(blank=True, default="")',
      '    status = models.CharField(max_length=32, blank=True, default="")',
    ]);
  });

  it("renders a choice field with its own tuple of pairs", () => {
    expect(renderModelFields(parseFields("status:choice(draft,sent)"), names)).toEqual([
      "    STATUS_CHOICES = (",
      '        ("draft", "Draft"),',
      '        ("sent", "Sent"),',
      "    )",
      '    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="draft")',
    ]);
  });

  it("an optional choice field's read type is never `| None` — it renders blank/default, never null (like str/text)", () => {
    expect(renderOutFields(parseFields("status:choice(draft,sent)?"))).toEqual(["    status: str"]);
  });

  it("an optional choice field's service param type is never `| None` for the same reason", () => {
    expect(renderCreateParams(parseFields("status:choice(draft,sent)?"))).toEqual([
      "    status: str,",
    ]);
  });

  it("renders a foreign key with a collision-free related_name", () => {
    expect(renderModelFields(parseFields("owner:fk(accounts.User)?"), names)).toEqual([
      "    owner = models.ForeignKey(",
      '        "accounts.User",',
      "        on_delete=models.PROTECT,",
      '        related_name="invoices_by_owner",',
      "        null=True,",
      "        blank=True,",
      "    )",
    ]);
  });
});
