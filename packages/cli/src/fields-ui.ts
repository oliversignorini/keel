/**
 * TypeScript-side renderers for `--ui`.
 *
 * `fields.ts` owns the `--fields` DSL and its Python renderers; this module
 * is the same idea for the four TSX files `templates/ui` writes. Each
 * function returns the lines that replace one `// keel:insert <slot>`
 * marker — plain string builders, not a second template language.
 *
 * Types map onto the same JSON shape `schemas.py` already produces
 * (fields.ts's `outType`/`renderOutFields`): a `decimal` travels as a
 * string ("2.00"), `date`/`datetime` as their ISO string, `fk` as the
 * related row's id (a string). There is no separate "TS type" DSL to keep
 * in sync — these renderers read the same `Field[]` the backend ones do.
 */

import type { Field } from "./fields.js";
import { displayField } from "./fields.js";
import type { Names } from "./naming.js";

function tsType(field: Field): string {
  switch (field.kind) {
    case "str":
    case "text":
    case "choice":
    case "decimal":
    case "date":
    case "datetime":
    case "fk":
      return "string";
    case "int":
      return "number";
    case "bool":
      return "boolean";
  }
}

function titleWords(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function fieldLabel(field: Field): string {
  return titleWords(field.name);
}

/** `lib/api.ts` — the write body interface's field declarations. */
export function renderWriteBodyFields(fields: Field[]): string[] {
  return fields.map((field) => `  ${field.name}${field.optional ? "?" : ""}: ${tsType(field)};`);
}

/**
 * `new/page.tsx` and `[id]/page.tsx` — the zod shape backing
 * react-hook-form. Validation is deliberately shallow (required-ness and,
 * for `str`, a max length matching the column) — the same "judgement stops
 * here" line `fields.ts` draws on the Python side.
 */
export function renderZodShape(fields: Field[]): string[] {
  return fields.map((field) => {
    const base = zodBase(field);
    return field.optional ? `  ${field.name}: ${base}.optional(),` : `  ${field.name}: ${base},`;
  });
}

function zodBase(field: Field): string {
  switch (field.kind) {
    case "str":
      return field.optional
        ? `z.string().max(${field.maxLength})`
        : `z.string().min(1, "${fieldLabel(field)} is required.").max(${field.maxLength})`;
    case "text":
      return "z.string()";
    case "choice":
      return "z.string()";
    case "int":
      return "z.coerce.number().int()";
    case "decimal":
      return field.optional ? "z.string()" : 'z.string().min(1, "Required.")';
    case "bool":
      return "z.boolean()";
    case "date":
    case "datetime":
      return field.optional ? "z.string()" : 'z.string().min(1, "Required.")';
    case "fk":
      return "z.string().uuid()";
  }
}

/** Whether a field renders as `<Select>` rather than a plain input — the
 * only field kind whose form control isn't a direct `<FormField>`/
 * `<FormTextarea>` pass-through. */
function isChoiceField(field: Field): boolean {
  return field.kind === "choice";
}

/**
 * `new/page.tsx` and `[id]/page.tsx` — the `<FormField>`/`<FormTextarea>`
 * elements for every non-choice field, in field order. Choice fields are
 * rendered separately (`renderChoiceFieldElements`) because they need the
 * per-resource `<___Resource___ChoiceField>` component, not `<FormField>`.
 */
export function renderFormFieldElements(fields: Field[], names: Names): string[] {
  const lines: string[] = [];
  for (const field of fields) {
    if (isChoiceField(field)) {
      lines.push(
        `        <${choiceFieldComponentName(field, names)} control={control} error={errors.${field.name}} />`,
      );
      continue;
    }
    const Component = field.kind === "text" ? "FormTextarea" : "FormField";
    const inputType = htmlInputType(field);
    lines.push(
      `        <${Component}`,
      `          label="${fieldLabel(field)}"`,
      `          id="${field.name}"`,
      ...(inputType ? [`          type="${inputType}"`] : []),
      `          error={errors.${field.name}?.message}`,
      `          {...register("${field.name}"${field.kind === "int" ? ", { valueAsNumber: true }" : ""})}`,
      `        />`,
    );
  }
  return lines;
}

function htmlInputType(field: Field): string | undefined {
  switch (field.kind) {
    case "int":
      return "number";
    case "bool":
      return "checkbox";
    case "date":
      return "date";
    case "datetime":
      return "datetime-local";
    default:
      return undefined;
  }
}

function pascal(snake: string): string {
  return snake
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
}

function kebab(snake: string): string {
  return snake.split("_").filter(Boolean).join("-");
}

/** `WidgetStatusField` for resource `Widget`, field `status` — matches
 * the hand-written `apps/web/.../_components/widget-status-field.tsx`
 * this template was extracted from. */
export function choiceFieldComponentName(field: Field, names: Names): string {
  return `${names.Resource}${pascal(field.name)}Field`;
}

/** `widget-status-field.tsx` — the file the component above lives in. */
export function choiceFieldFileName(field: Field, names: Names): string {
  return `${names.resource}-${kebab(field.name)}-field.tsx`;
}

/** `statusLabel` — the label helper a choice field's own component file
 * exports, imported wherever that field's value needs a human label
 * (the table column, the field itself). */
export function choiceLabelFnName(field: Field): string {
  return `${field.name}Label`;
}

/** `STATUS_OPTIONS` — the exported options constant a choice field's file
 * iterates to build its `<SelectItem>`s. */
export function choiceOptionsConstName(field: Field): string {
  return `${field.name.toUpperCase()}_OPTIONS`;
}

/** The literal form-values object type both `new/page.tsx` (via
 * `z.infer`) and a choice field's own file (which can't import a
 * page-local type) need — `{ name: string; description?: string }`. */
export function renderFormValuesType(fields: Field[]): string {
  if (fields.length === 0) return "Record<string, never>";
  const members = fields.map((f) => `${f.name}${f.optional ? "?" : ""}: ${tsType(f)}`);
  return `{ ${members.join("; ")} }`;
}

/**
 * The full source of a choice field's own component file — synthesized
 * directly rather than rendered from a `templates/ui` file, because it is
 * the one artifact `--fields` produces that is itself named after a field,
 * not the resource; `fields.ts` makes the same call for `models.py`'s
 * choice-field declaration (also generated as a whole unit, not templated
 * line by line). Mirrors `apps/web/.../widget-status-field.tsx`, generalized:
 * the per-value label is title-cased mechanically (`fields.ts`'s
 * `renderModelField` choice case does the same on the Python side) rather
 * than hand-picked, and the table badge is a single neutral variant rather
 * than a bespoke per-status color — a color mapping isn't something
 * `--fields` encodes, and inventing one would be the template designing,
 * not extracting.
 */
export function renderChoiceFieldFile(field: Field, names: Names, fields: Field[]): string {
  const Component = choiceFieldComponentName(field, names);
  const Options = choiceOptionsConstName(field);
  const labelFn = choiceLabelFnName(field);
  const formValuesType = renderFormValuesType(fields);
  const choices = field.choices!.map((c) => `"${c}"`).join(", ");

  return `"use client";

import { Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@keel/ui";
import { AlertCircle } from "lucide-react";
import { Controller, type Control, type FieldError } from "react-hook-form";

export const ${Options} = [${choices}] as const;

export function ${labelFn}(value: string): string {
  if (!value) return "—";
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

/** \`<${Component}>\` — \`@keel/ui\`'s \`<FormField>\` only wraps a native
 * \`<input>\`, so this composes the same label/error chrome around a Radix
 * \`<Select>\` via \`Controller\`. */
export function ${Component}({
  control,
  error,
}: {
  control: Control<${formValuesType}>;
  error?: FieldError;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="${field.name}">${field.name.charAt(0).toUpperCase()}${field.name.slice(1)}</Label>
      <Controller
        control={control}
        name="${field.name}"
        render={({ field }) => (
          <Select value={field.value || undefined} onValueChange={field.onChange}>
            <SelectTrigger id="${field.name}" aria-invalid={Boolean(error)} className="w-full">
              {/* Radix only learns an item's label once that item has
               * mounted — which happens on first open — so a value set
               * from async-loaded data (the edit form) would otherwise
               * show the placeholder until the user opens the dropdown.
               * Render the label explicitly instead of relying on that. */}
              <SelectValue placeholder="Select ${aOrAn(field.name)}">
                {field.value ? ${labelFn}(field.value) : undefined}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {${Options}.map((option) => (
                <SelectItem key={option} value={option}>
                  {${labelFn}(option)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      />
      {error ? (
        <p role="alert" className="flex items-center gap-1 text-sm text-destructive">
          <AlertCircle className="size-3.5 shrink-0" />
          {error.message}
        </p>
      ) : null}
    </div>
  );
}
`;
}

function aOrAn(word: string): string {
  return /^[aeiou]/i.test(word) ? `an ${word}` : `a ${word}`;
}

/**
 * `[id]/page.tsx` copy that names the row — a title, a breadcrumb, a
 * delete toast, a delete-confirmation heading — all built from the same
 * "what identifies this row to a human" field `fields.ts::displayField`
 * already picks for the backend's own tests. Without a display field
 * (e.g. a resource with no string-ish column) everything falls back to
 * the id, which is always available.
 */
export function renderDetailCopy(fields: Field[], names: Names): Record<string, string[]> {
  const display = displayField(fields);
  const displayValueLine = display
    ? `  const displayValue = ${names.resource} ? ${names.resource}.${display.name} : params.id;`
    : "  const displayValue = params.id;";
  return {
    display_value: [displayValueLine],
    delete_toast: [`    toast.success(\`\${displayValue} deleted\`);`],
    delete_dialog_title: [
      `            <AlertDialogTitle>Delete {displayValue}?</AlertDialogTitle>`,
    ],
  };
}

/**
 * `page.tsx` copy for the single-row delete flow — the list-page sibling
 * of `renderDetailCopy`, reading the deleted row directly rather than a
 * loaded-resource state variable.
 */
export function renderListCopy(fields: Field[], names: Names): Record<string, string[]> {
  const display = displayField(fields);
  const toastLine = display
    ? `    toast.success(\`\${row.${display.name}} deleted\`);`
    : `    toast.success("${names.Resource} deleted");`;
  const titleLine = display
    ? `            <AlertDialogTitle>Delete {rowPendingDelete?.${display.name}}?</AlertDialogTitle>`
    : `            <AlertDialogTitle>Delete this ${names.resource}?</AlertDialogTitle>`;
  return {
    row_delete_toast: [toastLine],
    row_delete_dialog_title: [titleLine],
  };
}

/** The properties inside the object literal the edit form seeds from the
 * loaded row — one `name: gizmo.name ?? "",` per field, dropped into the
 * `{ ... }` the template already wraps them in. */
export function renderEditDefaultValues(fields: Field[], names: Names): string[] {
  return fields.map((field) => {
    const accessor = `${names.resource}.${field.name}`;
    const value = field.kind === "bool" ? accessor : `${accessor} ?? ${emptyValue(field)}`;
    return `          ${field.name}: ${value},`;
  });
}

/** The value a missing field falls back to in the edit form's defaults —
 * matching `tsType`'s type for that field kind, so the fallback never
 * fights the zod-inferred `values` type it feeds. */
function emptyValue(field: Field): string {
  return field.kind === "int" ? "0" : '""';
}

/** `page.tsx` — one `<DataTable>` column per field, plus the linked
 * display column. Mirrors `fields.ts::displayField`: the first required
 * `str`/`text` field (or the first optional one) becomes the linked name
 * column; everything else is a plain or `<Badge>` column. */
export function renderColumns(fields: Field[], names: Names): string[] {
  const display = displayField(fields);
  const lines: string[] = [];
  for (const field of fields) {
    lines.push(...renderColumn(field, field === display, names));
  }
  return lines;
}

function renderColumn(field: Field, isDisplay: boolean, names: Names): string[] {
  const header = fieldLabel(field);
  if (isDisplay) {
    return [
      "      {",
      `        accessorKey: "${field.name}",`,
      `        header: "${header}",`,
      "        cell: ({ row }) => (",
      "          <Link",
      `            href={\`/\${currentOrg?.slug}/${names.resources}/\${row.original.id}\`}`,
      '            className="font-medium text-primary underline"',
      "          >",
      `            {row.original.${field.name}}`,
      "          </Link>",
      "        ),",
      "      },",
    ];
  }
  if (field.kind === "choice") {
    return [
      "      {",
      `        accessorKey: "${field.name}",`,
      `        header: "${header}",`,
      `        cell: ({ row }) => (`,
      `          <Badge variant="secondary">{${choiceLabelFnName(field)}(row.original.${field.name})}</Badge>`,
      `        ),`,
      "      },",
    ];
  }
  if (field.kind === "bool") {
    return [
      "      {",
      `        accessorKey: "${field.name}",`,
      `        header: "${header}",`,
      `        cell: ({ row }) => (row.original.${field.name} ? "Yes" : "No"),`,
      "      },",
    ];
  }
  return [
    "      {",
    `        accessorKey: "${field.name}",`,
    `        header: "${header}",`,
    "      },",
  ];
}

/** Every distinct choice field, for `_components/<field>-field.tsx` and
 * the imports/JSX referencing it. Two choice fields never collide because
 * each gets its own component named after the field, not the resource. */
export function choiceFields(fields: Field[]): Field[] {
  return fields.filter((f) => f.kind === "choice");
}

/** `page.tsx` — one import per choice field, label helper only (the list
 * page never renders the `<Select>`, only the value it produced). */
export function renderChoiceLabelImports(fields: Field[], names: Names): string[] {
  return choiceFields(fields).map(
    (f) =>
      `import { ${choiceLabelFnName(f)} } from "./_components/${choiceFieldModuleName(f, names)}";`,
  );
}

/** `new/page.tsx` / `[id]/page.tsx` — one import per choice field, the
 * `<Select>` component itself. */
export function renderChoiceFieldImports(fields: Field[], names: Names): string[] {
  return choiceFields(fields).map(
    (f) =>
      `import { ${choiceFieldComponentName(f, names)} } from "../_components/${choiceFieldModuleName(f, names)}";`,
  );
}

/** `gizmo-stage-field` — the module specifier for the file above (no
 * `.tsx`; a specifier that names its own extension is invalid ESM). */
function choiceFieldModuleName(field: Field, names: Names): string {
  return choiceFieldFileName(field, names).replace(/\.tsx$/, "");
}
