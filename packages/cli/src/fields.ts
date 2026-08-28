/**
 * The `--fields` DSL (docs/plans/phase-19.md 19.A "gen resource").
 *
 * Deliberately minimal, and deliberately not growing toward Django's field
 * API. Constraints, indexes, `Meta`, validators and cross-field rules are
 * judgement: the templates leave a marked insertion point and the slash
 * command drives an agent through filling it.
 *
 * Two additions beyond the plan's literal list, both forced by
 * `apps/api/keel/widgets/` having to regenerate from these templates
 * without a schema change (invariant 4 — no migration in this repo):
 *
 *   `str(32)`  an explicit max_length, because Widget.status is 32 and a
 *              255 default would be a column alteration, not a render.
 *   `name?`    "blank, defaults to empty/null", because Widget.description
 *              and Widget.status are both `blank=True, default=""` and an
 *              all-required model is wrong for most real resources anyway.
 *
 * Neither is an expression or a loop: both are one token of the field's
 * own declaration, which is the line this DSL exists to write.
 */

export type FieldKind =
  "str" | "text" | "int" | "decimal" | "bool" | "date" | "datetime" | "choice" | "fk";

export interface Field {
  /** Python attribute name, snake_case. */
  name: string;
  kind: FieldKind;
  /** True when the field was declared with a trailing `?`. */
  optional: boolean;
  /** `str(32)` -> 32. Only meaningful for `str`. */
  maxLength?: number;
  /** `choice(draft,sent)` -> ["draft", "sent"]. */
  choices?: string[];
  /** `fk(accounts.User)` -> { app: "accounts", model: "User" }. */
  target?: { app: string; model: string };
}

export class InvalidFieldSpec extends Error {}

const KNOWN_KINDS = new Set<string>([
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

const DEFAULT_MAX_LENGTH = 255;
const CHOICE_MAX_LENGTH = 32;

/**
 * Parses `"name:str,amount:decimal,status:choice(draft,sent)?"`.
 *
 * Splitting on "," naively would cut `choice(draft,sent)` in half, so this
 * scans character by character tracking parenthesis depth rather than
 * reaching for a regex that would need to encode the same state anyway.
 */
export function splitFieldSpecs(spec: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let current = "";
  for (const ch of spec) {
    if (ch === "(") depth += 1;
    if (ch === ")") depth -= 1;
    if (ch === "," && depth === 0) {
      parts.push(current);
      current = "";
      continue;
    }
    current += ch;
  }
  parts.push(current);
  if (depth !== 0) throw new InvalidFieldSpec(`Unbalanced parentheses in --fields: ${spec}`);
  return parts.map((p) => p.trim()).filter(Boolean);
}

export function parseFields(spec: string | undefined): Field[] {
  if (!spec || !spec.trim()) return [];
  return splitFieldSpecs(spec).map(parseField);
}

function parseField(raw: string): Field {
  const colon = raw.indexOf(":");
  if (colon === -1) {
    throw new InvalidFieldSpec(
      `Field "${raw}" is missing a type. Write it as name:type, e.g. amount:decimal.`,
    );
  }
  const name = raw.slice(0, colon).trim();
  let type = raw.slice(colon + 1).trim();

  if (!/^[a-z][a-z0-9_]*$/.test(name)) {
    throw new InvalidFieldSpec(
      `Field name "${name}" must be snake_case — it becomes a Python attribute and a column.`,
    );
  }
  if (name === "id" || name === "organization" || name === "created_by") {
    throw new InvalidFieldSpec(
      `Field name "${name}" is reserved: OrgScopedModel supplies id/organization and the ` +
        `template supplies created_by.`,
    );
  }

  let optional = false;
  if (type.endsWith("?")) {
    optional = true;
    type = type.slice(0, -1).trim();
  }

  const paren = type.indexOf("(");
  const kind = (paren === -1 ? type : type.slice(0, paren)).trim();
  if (!KNOWN_KINDS.has(kind)) {
    throw new InvalidFieldSpec(
      `Unknown field type "${kind}" in "${raw}". Supported: ${[...KNOWN_KINDS].join(", ")}. ` +
        `Anything past this list is judgement — leave it to the marked insertion point in models.py.`,
    );
  }
  let args: string[] = [];
  if (paren !== -1) {
    if (!type.endsWith(")")) throw new InvalidFieldSpec(`Unbalanced parentheses in "${raw}".`);
    const inner = type.slice(paren + 1, -1).trim();
    args = inner ? inner.split(",").map((a) => a.trim()) : [];
  }

  const field: Field = { name, kind: kind as FieldKind, optional };

  if (kind === "str") {
    if (args.length > 1) throw new InvalidFieldSpec(`str takes at most one length: "${raw}".`);
    if (args.length === 1) {
      const length = Number(args[0]);
      if (!Number.isInteger(length) || length < 1) {
        throw new InvalidFieldSpec(`str length must be a positive integer: "${raw}".`);
      }
      field.maxLength = length;
    } else {
      field.maxLength = DEFAULT_MAX_LENGTH;
    }
  } else if (args.length > 0 && kind !== "choice" && kind !== "fk") {
    throw new InvalidFieldSpec(`Field type "${kind}" takes no arguments: "${raw}".`);
  }

  if (kind === "choice") {
    if (args.length === 0) {
      throw new InvalidFieldSpec(
        `choice needs at least one value: "${raw}" — e.g. choice(draft,sent).`,
      );
    }
    for (const choice of args) {
      if (!/^[a-z][a-z0-9_]*$/.test(choice)) {
        throw new InvalidFieldSpec(
          `choice value "${choice}" must be snake_case — it is stored verbatim in the column.`,
        );
      }
    }
    field.choices = args;
  }

  if (kind === "fk") {
    if (args.length !== 1) {
      throw new InvalidFieldSpec(`fk takes exactly one target: "${raw}" — e.g. fk(accounts.User).`);
    }
    const target = args[0]!;
    const match = /^([a-z][a-z0-9_]*)\.([A-Z][A-Za-z0-9]*)$/.exec(target);
    if (!match) {
      throw new InvalidFieldSpec(
        `fk target "${target}" must be <app_label>.<Model>, e.g. fk(organizations.Organization).`,
      );
    }
    field.target = { app: match[1]!, model: match[2]! };
  }

  return field;
}

export function hasForeignKey(fields: Field[]): boolean {
  return fields.some((f) => f.kind === "fk");
}

/** Fields whose value the generated create/update services pass through. */
export function writableFields(fields: Field[]): Field[] {
  return fields;
}

// --- Renderers -------------------------------------------------------------
// Each returns the lines that replace one `# keel:insert <slot>` marker.
// They are plain string builders, not a template language: the template
// owns the file's shape and these own one declaration each.

function pythonQuote(value: string): string {
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

/** `models.py` field declarations. */
export function renderModelFields(fields: Field[], names: { resources: string }): string[] {
  const lines: string[] = [];
  for (const field of fields) {
    lines.push(...renderModelField(field, names));
  }
  return lines;
}

function renderModelField(field: Field, names: { resources: string }): string[] {
  const blank = field.optional;
  switch (field.kind) {
    case "str":
      return [
        `    ${field.name} = models.CharField(${joinKwargs([
          `max_length=${field.maxLength}`,
          ...(blank ? ["blank=True", 'default=""'] : []),
        ])})`,
      ];
    case "text":
      return [
        `    ${field.name} = models.TextField(${joinKwargs(
          blank ? ["blank=True", 'default=""'] : [],
        )})`,
      ];
    case "int":
      return [
        `    ${field.name} = models.IntegerField(${joinKwargs(
          blank ? ["null=True", "blank=True"] : [],
        )})`,
      ];
    case "decimal":
      return [
        `    ${field.name} = models.DecimalField(${joinKwargs([
          "max_digits=12",
          "decimal_places=2",
          ...(blank ? ["null=True", "blank=True"] : []),
        ])})`,
      ];
    case "bool":
      return [`    ${field.name} = models.BooleanField(default=False)`];
    case "date":
      return [
        `    ${field.name} = models.DateField(${joinKwargs(
          blank ? ["null=True", "blank=True"] : [],
        )})`,
      ];
    case "datetime":
      return [
        `    ${field.name} = models.DateTimeField(${joinKwargs(
          blank ? ["null=True", "blank=True"] : [],
        )})`,
      ];
    case "choice": {
      const choiceName = `${field.name.toUpperCase()}_CHOICES`;
      const rows = field.choices!.map(
        (choice) => `        (${pythonQuote(choice)}, ${pythonQuote(titleWords(choice))}),`,
      );
      return [
        `    ${choiceName} = (`,
        ...rows,
        `    )`,
        `    ${field.name} = models.CharField(${joinKwargs([
          `max_length=${CHOICE_MAX_LENGTH}`,
          `choices=${choiceName}`,
          ...(blank
            ? ["blank=True", 'default=""']
            : [`default=${pythonQuote(field.choices![0]!)}`]),
        ])})`,
      ];
    }
    case "fk": {
      const target = field.target!;
      const relatedName = `${names.resources}_by_${field.name}`;
      return [
        `    ${field.name} = models.ForeignKey(`,
        `        ${pythonQuote(`${target.app}.${target.model}`)},`,
        `        on_delete=models.PROTECT,`,
        `        related_name=${pythonQuote(relatedName)},`,
        ...(blank ? [`        null=True,`, `        blank=True,`] : []),
        `    )`,
      ];
    }
  }
}

function titleWords(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function joinKwargs(kwargs: string[]): string {
  return kwargs.join(", ");
}

/** Python type annotation for the read schema. */
function outType(field: Field): string {
  switch (field.kind) {
    case "str":
    case "text":
    case "choice":
      return "str";
    case "int":
      return "int";
    case "decimal":
      return "Decimal";
    case "bool":
      return "bool";
    case "date":
      return "date";
    case "datetime":
      return "datetime";
    case "fk":
      return "str";
  }
}

/** `schemas.py` — the read schema's field annotations. */
export function renderOutFields(fields: Field[]): string[] {
  const lines: string[] = [];
  for (const field of fields) {
    const optional = field.optional && field.kind !== "str" && field.kind !== "text";
    lines.push(`    ${field.name}: ${outType(field)}${optional ? " | None" : ""}`);
  }
  for (const field of fields) {
    if (field.kind !== "fk") continue;
    lines.push("");
    lines.push("    @staticmethod");
    lines.push(`    def resolve_${field.name}(obj: object) -> str:`);
    lines.push(`        return str(obj.${field.name}_id)  # type: ignore[attr-defined]`);
  }
  return lines;
}

/** `schemas.py` — the create schema. */
export function renderInFields(fields: Field[]): string[] {
  return fields.map((field) => {
    if (field.kind === "str") {
      const constraint = `Field(min_length=1, max_length=${field.maxLength})`;
      return field.optional
        ? `    ${field.name}: str = ""`
        : `    ${field.name}: str = ${constraint}`;
    }
    if (field.kind === "text" || field.kind === "choice") {
      return field.optional ? `    ${field.name}: str = ""` : `    ${field.name}: str`;
    }
    if (field.kind === "fk") {
      return field.optional ? `    ${field.name}: UUID | None = None` : `    ${field.name}: UUID`;
    }
    const type = outType(field);
    return field.optional
      ? `    ${field.name}: ${type} | None = None`
      : `    ${field.name}: ${type}`;
  });
}

/** `schemas.py` — the PATCH schema: every field optional, unset means unchanged. */
export function renderPatchFields(fields: Field[]): string[] {
  return fields.map((field) => {
    if (field.kind === "str") {
      return `    ${field.name}: str | None = Field(default=None, min_length=1, max_length=${field.maxLength})`;
    }
    if (field.kind === "text" || field.kind === "choice") {
      return `    ${field.name}: str | None = None`;
    }
    if (field.kind === "fk") {
      return `    ${field.name}: UUID | None = None`;
    }
    return `    ${field.name}: ${outType(field)} | None = None`;
  });
}

/** Imports `schemas.py` needs for the field types actually used. */
export function renderSchemaImports(fields: Field[]): string[] {
  const datetimeParts = new Set<string>(["datetime"]);
  const lines: string[] = [];
  if (fields.some((f) => f.kind === "date")) datetimeParts.add("date");
  lines.push(`from datetime import ${[...datetimeParts].sort().join(", ")}`);
  if (fields.some((f) => f.kind === "decimal")) lines.push("from decimal import Decimal");
  if (fields.some((f) => f.kind === "fk")) lines.push("from uuid import UUID");
  return lines;
}

/** `services.py` — keyword-only parameters on the create service. */
export function renderCreateParams(fields: Field[]): string[] {
  return fields.map((field) => `    ${field.name}: ${serviceParamType(field)},`);
}

function serviceParamType(field: Field): string {
  if (field.kind === "fk") return "Any";
  const type = outType(field);
  const optional = field.optional && field.kind !== "str" && field.kind !== "text";
  return optional ? `${type} | None` : type;
}

/** `services.py` — the `Model.objects.create(...)` keyword arguments. */
export function renderCreateKwargs(fields: Field[]): string[] {
  return fields.map((field) => `            ${field.name}=${field.name},`);
}

/** `views.py` — passing the validated payload through to the create service. */
export function renderCreateCallArgs(fields: Field[]): string[] {
  return fields.map((field) => `        ${field.name}=payload.${field.name},`);
}

/** `tests/factories.py` — the values a factory row is built with. */
export function renderFactoryKwargs(fields: Field[]): string[] {
  return fields.map((field) => `        ${field.name}=${sampleValue(field)},`);
}

/** `tests/test_services.py` — the same values, as a service call's kwargs. */
export function renderServiceCallKwargs(fields: Field[]): string[] {
  return fields.map((field) => `        ${field.name}=${sampleValue(field)},`);
}

function sampleValue(field: Field): string {
  switch (field.kind) {
    case "str":
      return pythonQuote(`A ${field.name}`.slice(0, Math.max(1, field.maxLength ?? 255)));
    case "text":
      return field.optional ? '""' : pythonQuote("Some text");
    case "int":
      return "1";
    case "decimal":
      return 'Decimal("1.00")';
    case "bool":
      return "False";
    case "date":
      return "date(2026, 1, 1)";
    case "datetime":
      return "datetime(2026, 1, 1, tzinfo=UTC)";
    case "choice":
      return field.optional ? '""' : pythonQuote(field.choices![0]!);
    case "fk":
      return "None";
  }
}

/** The JSON body a generated API test POSTs — required fields only. */
export function renderApiCreateBody(fields: Field[]): string {
  const required = fields.filter((f) => !f.optional && f.kind !== "fk");
  const pairs = required.map((f) => `${pythonQuote(f.name)}: ${jsonSampleValue(f)}`);
  return `{${pairs.join(", ")}}`;
}

function jsonSampleValue(field: Field): string {
  switch (field.kind) {
    case "str":
      return pythonQuote(`A ${field.name}`.slice(0, Math.max(1, field.maxLength ?? 255)));
    case "text":
      return pythonQuote("Some text");
    case "int":
      return "1";
    case "decimal":
      return pythonQuote("1.00");
    case "bool":
      return "False";
    case "date":
      return pythonQuote("2026-01-01");
    case "datetime":
      return pythonQuote("2026-01-01T00:00:00Z");
    case "choice":
      return pythonQuote(field.choices![0]!);
    case "fk":
      return "None";
  }
}

/** The first required string-ish field — what a test asserts a value on. */
export function displayField(fields: Field[]): Field | undefined {
  return (
    fields.find((f) => !f.optional && (f.kind === "str" || f.kind === "text")) ??
    fields.find((f) => f.kind === "str" || f.kind === "text")
  );
}

/** Extra `select_related` targets a list selector needs to stay one query. */
export function renderSelectRelated(fields: Field[]): string {
  const targets = ["created_by", ...fields.filter((f) => f.kind === "fk").map((f) => f.name)];
  return targets.map((t) => pythonQuote(t)).join(", ");
}
