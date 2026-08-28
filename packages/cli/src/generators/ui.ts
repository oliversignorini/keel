/**
 * `--ui` (docs/plans/phase-19.md 19.C). `apps/web/app/(app)/app/[org]/
 * widgets/` **is** the template — extracted, not designed — and
 * `packages/ui`'s `data-table`, `resource-form`, `form-field`,
 * `empty-state` and `page-header` are the only primitives a generated
 * page is allowed to assemble. If a field kind ever needed a component
 * `packages/ui` doesn't have, that would be a signal to add it there, not
 * to invent one in a template — no field kind here does.
 *
 * Called from `generateResource` (resource.ts) when `--ui` is passed;
 * this module only adds to the `Plan` that function already built, so a
 * dry run, the write, and the file/splice report are all one code path.
 */

import * as fs from "node:fs";
import * as path from "node:path";

import { spliceFrontendPermission, spliceNavItem } from "../anchors.js";
import {
  choiceFieldFileName,
  choiceFields,
  renderChoiceFieldFile,
  renderChoiceFieldImports,
  renderChoiceLabelImports,
  renderColumns,
  renderDetailCopy,
  renderEditDefaultValues,
  renderFormFieldElements,
  renderListCopy,
  renderWriteBodyFields,
  renderZodShape,
} from "../fields-ui.js";
import type { Field } from "../fields.js";
import type { Names } from "../naming.js";
import type { Plan } from "../plan.js";
import type { Repo } from "../repo.js";
import { webSpliceTargets } from "../repo.js";
import { render, renderPath } from "../template.js";

export class UiGeneratorError extends Error {}

const UI_TEMPLATE_DIR = "ui";

function listTemplateFiles(dir: string, prefix = ""): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const relPath = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) {
      out.push(...listTemplateFiles(path.join(dir, entry.name), relPath));
    } else if (entry.isFile()) {
      out.push(relPath);
    }
  }
  return out.sort();
}

/** `page.tsx` -> `apps/web/app/(app)/app/[org]/<resources>/page.tsx`;
 * `lib/api.ts` -> `apps/web/lib/<resources>/api.ts` — the one file that
 * doesn't live under the route directory, same split the hand-written
 * `apps/web/lib/widgets/api.ts` / `.../widgets/page.tsx` already use. */
function destFor(relPath: string, names: Names, webDir: string): string {
  if (relPath.startsWith("lib/")) {
    return path.join(webDir, "lib", names.resources, relPath.slice("lib/".length));
  }
  return path.join(webDir, "app", "(app)", "app", "[org]", names.resources, relPath);
}

export interface UiOptions {
  permissionScheme: "crud" | "manage";
}

/**
 * Adds `--ui`'s files and splices to an already-built backend `Plan`.
 * Read-only resources aren't supported yet — a page with no write paths
 * is a real UI shape (`--no-ui` combined with an admin-only `views.py` is
 * the near-term answer), but composing `<ResourceForm>` out of primitives
 * that assume create/update makes it a second, bigger job than this
 * slice's fields warrant. Failing loudly here beats silently emitting a
 * broken create page.
 */
export function planUi(
  repo: Repo,
  names: Names,
  fields: Field[],
  options: UiOptions,
  readonly: boolean,
  plan: Plan,
  dryRun: boolean,
): void {
  if (readonly) {
    throw new UiGeneratorError(
      "`--ui` does not support `readonly-resource` yet (docs/plans/phase-19.md 19.C). " +
        "Pass `--no-ui`, or run `gen resource` instead.",
    );
  }

  const templatesRoot = path.join(repo.templatesDir, UI_TEMPLATE_DIR);
  if (!fs.existsSync(templatesRoot)) {
    throw new UiGeneratorError(`Templates not found at ${templatesRoot}.`);
  }
  const webDir = path.join(repo.root, "apps", "web");

  const flags = new Set<string>();
  flags.add(options.permissionScheme === "crud" ? "crud_permissions" : "manage_permissions");
  if (fields.length > 0) flags.add("has_fields");
  else flags.add("no_fields");
  if (fields.some((f) => f.kind === "text")) flags.add("has_text");
  if (choiceFields(fields).length > 0) flags.add("has_choice");

  const inserts: Record<string, string[]> = {
    columns: renderColumns(fields, names),
    choice_label_imports: renderChoiceLabelImports(fields, names),
    choice_field_imports: renderChoiceFieldImports(fields, names),
    write_body_fields: renderWriteBodyFields(fields),
    zod_shape: renderZodShape(fields),
    form_fields: renderFormFieldElements(fields, names),
    edit_default_values: renderEditDefaultValues(fields, names),
    ...renderDetailCopy(fields, names),
    ...renderListCopy(fields, names),
  };

  for (const relPath of listTemplateFiles(templatesRoot)) {
    const templatePath = path.join(templatesRoot, relPath);
    const source = fs.readFileSync(templatePath, "utf8");
    const contents = render(source, { names, flags, inserts }, relPath);
    const dest = destFor(renderPath(relPath, names), names, webDir);
    plan.add(dest, contents);
  }

  // Choice fields each get their own file, synthesized rather than
  // rendered from a fixed template — see fields-ui.ts::renderChoiceFieldFile.
  for (const field of choiceFields(fields)) {
    const dest = path.join(
      webDir,
      "app",
      "(app)",
      "app",
      "[org]",
      names.resources,
      "_components",
      choiceFieldFileName(field, names),
    );
    plan.add(dest, renderChoiceFieldFile(field, names, fields));
  }

  const webTargets = webSpliceTargets(repo);
  const viewConstant =
    options.permissionScheme === "crud" ? `${names.RESOURCE}_VIEW` : `${names.RESOURCES}_VIEW`;

  const codes =
    options.permissionScheme === "crud"
      ? [
          { constant: `${names.RESOURCE}_VIEW`, code: `${names.resource}.view` },
          { constant: `${names.RESOURCE}_CREATE`, code: `${names.resource}.create` },
          { constant: `${names.RESOURCE}_UPDATE`, code: `${names.resource}.update` },
          { constant: `${names.RESOURCE}_DELETE`, code: `${names.resource}.delete` },
        ]
      : [
          { constant: `${names.RESOURCES}_VIEW`, code: `${names.resources}.view` },
          { constant: `${names.RESOURCES}_MANAGE`, code: `${names.resources}.manage` },
        ];

  for (const code of codes) {
    plan.splices.push(spliceFrontendPermission(webTargets, code, dryRun));
  }
  plan.splices.push(
    spliceNavItem(
      webTargets,
      { resources: names.resources, label: names.Resources, viewConstant },
      dryRun,
    ),
  );
}
