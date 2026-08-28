import { describe, expect, it } from "vitest";

import {
  choiceFieldComponentName,
  choiceFieldFileName,
  choiceFields,
  choiceLabelFnName,
  choiceOptionsConstName,
  renderChoiceFieldFile,
  renderColumns,
  renderDetailCopy,
  renderEditDefaultValues,
  renderFormFieldElements,
  renderFormValuesType,
  renderListCopy,
  renderWriteBodyFields,
  renderZodShape,
} from "./fields-ui.js";
import { parseFields } from "./fields.js";
import { namesFor } from "./naming.js";

const names = namesFor("Gizmo");

describe("renderWriteBodyFields", () => {
  it("marks optional fields with `?` and maps kinds to TS types", () => {
    const fields = parseFields("title:str,notes:text?,qty:int,active:bool,cost:decimal");
    expect(renderWriteBodyFields(fields)).toEqual([
      "  title: string;",
      "  notes?: string;",
      "  qty: number;",
      "  active: boolean;",
      "  cost: string;",
    ]);
  });
});

describe("renderZodShape", () => {
  it("adds .optional() only for optional fields", () => {
    const fields = parseFields("title:str,notes:text?");
    const lines = renderZodShape(fields);
    expect(lines[0]).toContain("title: z.string()");
    expect(lines[0]).not.toContain(".optional()");
    expect(lines[1]).toContain("notes: z.string().optional()");
  });

  it("coerces int fields to a number", () => {
    expect(renderZodShape(parseFields("qty:int"))[0]).toBe("  qty: z.coerce.number().int(),");
  });
});

describe("renderFormValuesType", () => {
  it("builds the literal type a choice field's Control<> needs", () => {
    expect(renderFormValuesType(parseFields("title:str,notes:text?"))).toBe(
      "{ title: string; notes?: string }",
    );
  });

  it("falls back to Record<string, never> with no fields", () => {
    expect(renderFormValuesType([])).toBe("Record<string, never>");
  });
});

describe("choice fields", () => {
  const fields = parseFields("title:str,stage:choice(draft,live)");
  const [, stage] = fields;

  it("finds only the choice fields", () => {
    expect(choiceFields(fields)).toEqual([stage]);
  });

  it("names the component and file after the resource and field", () => {
    expect(choiceFieldComponentName(stage!, names)).toBe("GizmoStageField");
    expect(choiceFieldFileName(stage!, names)).toBe("gizmo-stage-field.tsx");
    expect(choiceLabelFnName(stage!)).toBe("stageLabel");
    expect(choiceOptionsConstName(stage!)).toBe("STAGE_OPTIONS");
  });

  it("synthesizes a self-contained component with title-cased labels", () => {
    const content = renderChoiceFieldFile(stage!, names, fields);
    expect(content).toContain('export const STAGE_OPTIONS = ["draft", "live"] as const;');
    expect(content).toContain("export function stageLabel(value: string): string {");
    expect(content).toContain("export function GizmoStageField({");
    expect(content).toContain("Control<{ title: string; stage: string }>");
  });
});

describe("renderFormFieldElements", () => {
  it("renders a choice field as its own component, not <FormField>", () => {
    const fields = parseFields("stage:choice(draft,live)");
    const lines = renderFormFieldElements(fields, names);
    expect(lines.join("\n")).toContain(
      "<GizmoStageField control={control} error={errors.stage} />",
    );
  });

  it("renders text fields as <FormTextarea>, others as <FormField>", () => {
    const fields = parseFields("title:str,notes:text?");
    const lines = renderFormFieldElements(fields, names).join("\n");
    expect(lines).toContain("<FormField");
    expect(lines).toContain("<FormTextarea");
  });
});

describe("renderEditDefaultValues", () => {
  it("falls back to a type-matching empty value per field kind", () => {
    const fields = parseFields("title:str,qty:int,active:bool");
    const lines = renderEditDefaultValues(fields, names);
    expect(lines).toEqual([
      '          title: gizmo.title ?? "",',
      "          qty: gizmo.qty ?? 0,",
      "          active: gizmo.active,",
    ]);
  });
});

describe("renderDetailCopy / renderListCopy", () => {
  it("names the row from the display field when one exists", () => {
    const fields = parseFields("title:str,qty:int");
    const detail = renderDetailCopy(fields, names);
    expect(detail.display_value).toEqual([
      "  const displayValue = gizmo ? gizmo.title : params.id;",
    ]);
    expect(detail.delete_toast).toEqual(["    toast.success(`${displayValue} deleted`);"]);

    const list = renderListCopy(fields, names);
    expect(list.row_delete_toast).toEqual(["    toast.success(`${row.title} deleted`);"]);
  });

  it("falls back to the id / a generic noun with no display field", () => {
    const fields = parseFields("qty:int");
    const detail = renderDetailCopy(fields, names);
    expect(detail.display_value).toEqual(["  const displayValue = params.id;"]);

    const list = renderListCopy(fields, names);
    expect(list.row_delete_toast).toEqual(['    toast.success("Gizmo deleted");']);
    expect(list.row_delete_dialog_title).toEqual([
      "            <AlertDialogTitle>Delete this gizmo?</AlertDialogTitle>",
    ]);
  });
});

describe("renderColumns", () => {
  it("makes the display field a link, and a choice field a labeled badge", () => {
    const fields = parseFields("title:str,stage:choice(draft,live)");
    const rendered = renderColumns(fields, names).join("\n");
    expect(rendered).toContain("href={`/${currentOrg?.slug}/gizmos/${row.original.id}`}");
    expect(rendered).toContain("stageLabel(row.original.stage)");
  });
});
