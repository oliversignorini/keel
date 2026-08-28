/**
 * `gen resource` and `gen readonly-resource` (docs/plans/phase-19.md 19.A).
 *
 * One implementation for both: a read-only resource is a resource with the
 * write paths removed, which is a set of files not emitted and one flag in
 * the templates — not a second generator that will drift from this one.
 */

import * as fs from "node:fs";
import * as path from "node:path";

import { splicePermission, spliceInstalledApps, spliceRouter } from "../anchors.js";
import { planUi } from "./ui.js";
import type { Field } from "../fields.js";
import {
  displayField,
  hasForeignKey,
  parseFields,
  renderApiCreateBody,
  renderCreateCallArgs,
  renderCreateKwargs,
  renderCreateParams,
  renderFactoryKwargs,
  renderInFields,
  renderModelFields,
  renderOutFields,
  renderPatchFields,
  renderSchemaImports,
  renderSelectRelated,
  renderServiceCallKwargs,
} from "../fields.js";
import { formatPython } from "../format.js";
import { formatTs } from "../format-ts.js";
import type { Names } from "../naming.js";
import { namesFor } from "../naming.js";
import { Plan, reportPlan } from "../plan.js";
import type { Repo } from "../repo.js";
import { loadRepo, rel, spliceTargets } from "../repo.js";
import { render, renderPath } from "../template.js";
import { makeMigrations, reportGates, runDbFreeGates } from "../verify.js";

export interface ResourceOptions {
  name: string;
  fields?: string;
  ui: boolean;
  dryRun: boolean;
  force: boolean;
  verify: boolean;
  readonly: boolean;
  /**
   * `crud` (default) emits four codes — <resource>.view/.create/.update/
   * .delete. `manage` emits the coarser <resources>.view/.manage pair the
   * repository's own reference slice was hand-written with, and is what
   * lets that slice regenerate from these templates without a permission
   * rename rippling through the frontend and the seeded roles.
   */
  permissionScheme: "crud" | "manage";
}

export class GeneratorError extends Error {}

const RESOURCE_TEMPLATE_DIR = "resource";
const READONLY_TEMPLATE_DIR = "readonly-resource";

/** Files a read-only resource does not have. */
const READONLY_EXCLUDED = new Set([
  "services.py",
  "tasks.py",
  "tests/test_services.py",
  "tests/test_tasks.py",
  "tests/test_audit_coverage.py",
]);

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

/**
 * The template set for one generator: `readonly-resource/` overlays
 * `resource/` rather than duplicating it. A read-only slice differs in
 * three files (schemas, views, the API test) and is identical in the other
 * nine; two full copies would mean every future template fix has to be
 * made twice, and the second copy is the one that gets forgotten.
 */
function resolveTemplates(repo: Repo, readonly: boolean): Map<string, string> {
  const base = path.join(repo.templatesDir, RESOURCE_TEMPLATE_DIR);
  if (!fs.existsSync(base)) {
    throw new GeneratorError(`Templates not found at ${rel(repo, base)}.`);
  }
  const files = new Map<string, string>();
  for (const relPath of listTemplateFiles(base)) {
    if (readonly && READONLY_EXCLUDED.has(relPath)) continue;
    files.set(relPath, path.join(base, relPath));
  }
  if (readonly) {
    const overlay = path.join(repo.templatesDir, READONLY_TEMPLATE_DIR);
    if (!fs.existsSync(overlay)) {
      throw new GeneratorError(`Templates not found at ${rel(repo, overlay)}.`);
    }
    for (const relPath of listTemplateFiles(overlay)) {
      files.set(relPath, path.join(overlay, relPath));
    }
  }
  return files;
}

function permissionCodes(
  names: Names,
  scheme: "crud" | "manage",
): Array<{ constant: string; code: string }> {
  if (scheme === "manage") {
    const upper = names.resources.toUpperCase();
    return [
      { constant: `${upper}_VIEW`, code: `${names.resources}.view` },
      { constant: `${upper}_MANAGE`, code: `${names.resources}.manage` },
    ];
  }
  const upper = names.resource.toUpperCase();
  return [
    { constant: `${upper}_VIEW`, code: `${names.resource}.view` },
    { constant: `${upper}_CREATE`, code: `${names.resource}.create` },
    { constant: `${upper}_UPDATE`, code: `${names.resource}.update` },
    { constant: `${upper}_DELETE`, code: `${names.resource}.delete` },
  ];
}

function buildInserts(
  names: Names,
  fields: Field[],
  options: ResourceOptions,
): Record<string, string[]> {
  const display = displayField(fields);
  const patchTarget =
    fields.find((f) => f.kind === "choice") ??
    fields.find((f) => f.optional && (f.kind === "str" || f.kind === "text")) ??
    display;

  const inserts: Record<string, string[]> = {
    model_fields: renderModelFields(fields, names),
    model_str: display
      ? ["    def __str__(self) -> str:", `        return self.${display.name}`]
      : [
          "    def __str__(self) -> str:",
          `        return f"${names.Resource} {self.pk}"`.replace("{self.pk}", "{self.pk}"),
        ],
    fk_select_related: fields
      .filter((f) => f.kind === "fk")
      .map((f) => `        "${f.name}",`)
      .concat(['        "created_by",']),
    schema_imports: renderSchemaImports(fields),
    out_fields: renderOutFields(fields),
    in_fields: renderInFields(fields),
    patch_fields: renderPatchFields(fields),
    service_imports: sampleImports(fields, { includeUtc: false }),
    create_params: renderCreateParams(fields),
    create_kwargs: renderCreateKwargs(fields),
    create_call_args: renderCreateCallArgs(fields),
    factory_imports: sampleImports(fields),
    factory_kwargs: renderFactoryKwargs(fields),
    service_test_imports: sampleImports(fields),
    service_call_kwargs: renderServiceCallKwargs(fields),
    update_assertions: renderUpdateAssertions(fields, patchTarget),
    api_create_body: [`_CREATE_BODY = ${renderApiCreateBody(fields)}`],
    api_retrieve_assertions: display
      ? [`    assert response.json()["${display.name}"] == _CREATE_BODY["${display.name}"]`]
      : [],
    api_patch_assertions: renderApiPatchAssertions(names, patchTarget),
    api_validation_test: renderApiValidationTest(names, fields),
  };
  void options;
  return inserts;
}

/**
 * The `datetime`/`decimal` imports a rendered file needs. Tests also need
 * `UTC` to build an aware datetime literal; `services.py` only names the
 * types in annotations, so it does not.
 */
function sampleImports(fields: Field[], opts: { includeUtc: boolean } = { includeUtc: true }) {
  const datetimeParts: string[] = [];
  if (fields.some((f) => f.kind === "date")) datetimeParts.push("date");
  if (fields.some((f) => f.kind === "datetime")) {
    datetimeParts.push("datetime");
    if (opts.includeUtc) datetimeParts.push("UTC");
  }
  const lines: string[] = [];
  if (datetimeParts.length > 0) {
    lines.push(`from datetime import ${[...new Set(datetimeParts)].sort().join(", ")}`);
  }
  if (fields.some((f) => f.kind === "decimal")) lines.push("from decimal import Decimal");
  if (lines.length > 0) lines.push("");
  return lines;
}

function renderUpdateAssertions(fields: Field[], target: Field | undefined): string[] {
  if (!target) {
    return [
      "    updated = services.update___resource__(__resource__=row, actor=creator)",
      "",
      "    assert updated.pk == row.pk",
    ];
  }
  const value = updateSampleValue(target);
  const other = fields.find((f) => f !== target && (f.kind === "str" || f.kind === "text"));
  const lines = [
    `    updated = services.update___resource__(`,
    `        __resource__=row, actor=creator, ${target.name}=${value}`,
    `    )`,
    "",
    "    updated.refresh_from_db()",
    `    assert updated.${target.name} == ${value}`,
  ];
  if (other) {
    lines.push(
      `    assert updated.${other.name} == row.${other.name}  # untouched fields stay untouched`,
    );
  }
  return lines;
}

function updateSampleValue(field: Field): string {
  switch (field.kind) {
    case "choice":
      return `"${field.choices![field.choices!.length - 1]!}"`;
    case "int":
      return "2";
    case "decimal":
      return 'Decimal("2.00")';
    case "bool":
      return "True";
    case "date":
      return "date(2026, 6, 1)";
    case "datetime":
      return "datetime(2026, 6, 1, tzinfo=UTC)";
    default:
      return '"changed"';
  }
}

function renderApiPatchAssertions(names: Names, target: Field | undefined): string[] {
  if (!target || target.kind === "fk") return [];
  const value = updateSampleValue(target).replace(/^Decimal\("(.*)"\)$/, '"$1"');
  const jsonValue =
    target.kind === "date" || target.kind === "datetime"
      ? '"2026-06-01"'
      : target.kind === "bool"
        ? "True"
        : value;
  const expected = target.kind === "decimal" ? '"2.00"' : jsonValue;
  return [
    "    response = client.patch(",
    `        f"/api/v1/orgs/{org.slug}/${names.resources}/{row_id}/",`,
    `        {"${target.name}": ${jsonValue}},`,
    '        content_type="application/json",',
    "    )",
    "    assert response.status_code == 200, response.content",
    `    assert response.json()["${target.name}"] == ${expected}`,
    "",
  ];
}

/**
 * A validation test only exists when there is a field whose validation
 * can actually fail. A generated test asserting a 400 that the schema
 * cannot produce is a test that documents a lie.
 */
function renderApiValidationTest(names: Names, fields: Field[]): string[] {
  const required = fields.find((f) => !f.optional && f.kind === "str");
  if (!required) return [];
  return [
    "def test_create_rejects_a_blank_required_field_with_400() -> None:",
    "    org, owner = _org_with_owner()",
    "    client = _client_for(owner)",
    "",
    "    response = client.post(",
    `        f"/api/v1/orgs/{org.slug}/${names.resources}/",`,
    `        {**_CREATE_BODY, "${required.name}": ""},`,
    '        content_type="application/json",',
    "    )",
    "",
    "    assert response.status_code == 400",
    '    fields = {row["field"] for row in response.json()["error"]["details"]}',
    `    assert "${required.name}" in fields`,
  ];
}

export function generateResource(options: ResourceOptions): number {
  const repo = loadRepo();
  const names = namesFor(options.name);
  const fields = parseFields(options.fields);
  const appDir = path.join(repo.packageDir, names.app);

  if (fs.existsSync(appDir) && !options.force) {
    console.error(
      `${rel(repo, appDir)} already exists. Re-running the generator over an existing ` +
        `app would overwrite hand-written domain logic, so it refuses by default. ` +
        `Pass --force if regenerating it is what you want. Nothing was written.`,
    );
    return 1;
  }

  const flags = new Set<string>();
  flags.add(hasForeignKey(fields) ? "fk" : "no_fk");
  flags.add(options.permissionScheme === "crud" ? "crud_permissions" : "manage_permissions");
  if (options.readonly) flags.add("readonly");

  const inserts = buildInserts(names, fields, options);
  const templates = resolveTemplates(repo, options.readonly);

  const plan = new Plan();
  for (const [relPath, templatePath] of templates) {
    const source = fs.readFileSync(templatePath, "utf8");
    const contents = render(source, { names, flags, inserts }, rel(repo, templatePath));
    plan.add(path.join(appDir, renderPath(relPath, names)), contents);
  }

  // The migration is produced by `makemigrations`, never by a template:
  // Django's own writer is the only thing that can be trusted to describe
  // the model it was just handed. An existing one is left strictly alone —
  // CLAUDE.md invariant 4 is one baseline migration per app, and rewriting
  // a committed migration is a schema edit wearing a generator's clothes.
  const migrationPath = path.join(appDir, "migrations", "0001_initial.py");
  const migrationExists = fs.existsSync(migrationPath);
  if (migrationExists) {
    plan.skip(migrationPath, "already exists — a committed migration is never regenerated");
  }

  const targets = spliceTargets(repo);
  const codes = permissionCodes(names, options.permissionScheme);

  // Splices are computed against the current file contents, and in dry-run
  // mode applySpec is told not to write. Same code path either way — a
  // second "what would happen" implementation is a second thing to drift.
  for (const code of codes) {
    plan.splices.push(...splicePermission(targets, code, options.dryRun));
  }
  plan.splices.push(
    spliceInstalledApps(
      targets,
      { pythonPackage: repo.pythonPackage, app: names.app },
      options.dryRun,
    ),
  );
  plan.splices.push(
    ...spliceRouter(
      targets,
      { pythonPackage: repo.pythonPackage, app: names.app },
      repo.tenantSegment,
      options.dryRun,
    ),
  );

  if (options.ui) {
    try {
      planUi(
        repo,
        names,
        fields,
        { permissionScheme: options.permissionScheme },
        options.readonly,
        plan,
        options.dryRun,
      );
    } catch (error) {
      console.error(`gen resource --ui: ${error instanceof Error ? error.message : String(error)}`);
      return 2;
    }
  }

  if (options.dryRun) {
    if (!migrationExists) {
      plan.skip(
        migrationPath,
        "would be written by `manage.py makemigrations` after the app files",
      );
    }
    reportPlan(repo, plan, true);
    console.log("\n--dry-run: nothing was written.");
    return 0;
  }

  plan.write();

  if (!migrationExists) {
    const result = makeMigrations(repo, names.app);
    if (!result.ok) {
      console.error(`\nFAILED: ${result.command}\n${result.output}`);
      return 1;
    }
    plan.add(migrationPath, "");
  }

  const spliceFiles = [...new Set(plan.splices.map((s) => s.file))];
  const pythonSpliceFiles = spliceFiles.filter((f) => f.endsWith(".py"));
  const tsSpliceFiles = spliceFiles.filter((f) => f.endsWith(".ts") || f.endsWith(".tsx"));

  const formatted = formatPython(repo, [appDir, ...pythonSpliceFiles]);
  if (!formatted.ok) {
    plan.note(`  note: ${formatted.message}`);
  }

  if (options.ui) {
    const webFiles = [...plan.files.filter((f) => !f.skipReason).map((f) => f.absolutePath)].filter(
      (f) => f.includes(`${path.sep}apps${path.sep}web${path.sep}`),
    );
    const formattedTs = formatTs(repo, [...webFiles, ...tsSpliceFiles]);
    if (!formattedTs.ok) {
      plan.note(`  note: ${formattedTs.message}`);
    }
  }

  reportPlan(repo, plan, false);

  plan.note("");
  console.log(
    `\nNext, and not done for you:\n` +
      `  - fill in the business rules in ${rel(repo, path.join(appDir, "services.py"))}\n` +
      `  - add any bespoke permission code (e.g. "${names.resource}.export") with ` +
      `\`pnpm gen permission\`\n` +
      `  - run \`pnpm gen sync-client\` in whichever worktree owns the generated client ` +
      `this wave — this generator never regenerates it.`,
  );

  if (!options.verify) {
    console.log("\n--no-verify: the DB-free gates were not run.");
    return 0;
  }

  const gates = runDbFreeGates(repo);
  return reportGates(gates) ? 0 : 1;
}
