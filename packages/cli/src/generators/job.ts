/**
 * `gen job <Name>` (docs/plans/phase-19.md 19.B) — ports the mechanical
 * half of `.claude/commands/new-job.md`.
 *
 * CLAUDE.md invariant 5 splits async work into two tiers, and the split
 * is a judgement call the generator does not make for the caller: `--tier`
 * is required, not defaulted, so the decision new-job.md asks a human (or
 * agent) to make explicitly stays explicit here too.
 *
 *   --tier 1   Single-step, fire-and-forget. One `@task`-decorated
 *              function appended to an *existing* app's `tasks.py`,
 *              delegating to a service function of the same name that is
 *              left for the caller to write — the same "insertion point,
 *              not invented logic" shape `gen resource` leaves in
 *              `services.py`. Requires `--app <app>`.
 *   --tier 2   Multi-step, resumable, follows `keel/jobs/demo.py`'s shape:
 *              a step-function-per-step module under `keel/jobs/`, spliced
 *              into `JobsConfig.ready()`, with generated tests covering
 *              each step, resumption after a simulated crash, and running
 *              the same job twice.
 *
 * Neither tier writes a migration — a job type is Python, not a model —
 * so there is no DB step here the way `gen resource` has one for
 * `makemigrations`.
 */

import * as fs from "node:fs";
import * as path from "node:path";

import { spliceJobRegistration } from "../anchors.js";
import { formatPython } from "../format.js";
import type { Names } from "../naming.js";
import { namesFor } from "../naming.js";
import { Plan, reportPlan } from "../plan.js";
import type { Repo } from "../repo.js";
import { loadRepo, rel } from "../repo.js";
import { render, renderPath } from "../template.js";
import { reportGates, runDbFreeGates } from "../verify.js";

export interface JobOptions {
  name: string;
  tier: 1 | 2;
  /** Tier 2 only: comma-separated step names. Defaults to a single "run" step. */
  steps?: string;
  /** Tier 1 only: the existing app whose tasks.py gets the new task. */
  app?: string;
  /** Tier 1 only: the service function name to delegate to. Defaults to the job's own name. */
  service?: string;
  dryRun: boolean;
  force: boolean;
  verify: boolean;
}

export class GeneratorError extends Error {}

const STEP_NAME_RE = /^[a-z][a-z0-9_]*$/;

export function parseSteps(spec: string | undefined): string[] {
  if (!spec || !spec.trim()) return ["run"];
  const names = spec
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (names.length === 0) return ["run"];
  const seen = new Set<string>();
  for (const name of names) {
    if (!STEP_NAME_RE.test(name)) {
      throw new GeneratorError(
        `Step name "${name}" must be snake_case — it becomes a Python function name.`,
      );
    }
    if (seen.has(name)) {
      throw new GeneratorError(`Step name "${name}" is repeated in --steps.`);
    }
    seen.add(name);
  }
  return names;
}

export function generateJob(options: JobOptions): number {
  if (options.tier !== 1 && options.tier !== 2) {
    throw new GeneratorError(
      `\`gen job\` needs --tier 1 or --tier 2 (docs/plans/phase-19.md 19.B, CLAUDE.md ` +
        `invariant 5) — this generator will not guess which one your job is. Tier 1: single ` +
        `step, fire-and-forget. Tier 2: multi-step, resumable. Ask if it isn't obvious.`,
    );
  }
  const repo = loadRepo();
  const names = namesFor(options.name);
  return options.tier === 1
    ? generateTier1(repo, names, options)
    : generateTier2(repo, names, options);
}

// --- Tier 1 -----------------------------------------------------------

function generateTier1(repo: Repo, names: Names, options: JobOptions): number {
  if (!options.app) {
    throw new GeneratorError(
      `\`--tier 1\` needs \`--app <app>\` — the existing app whose tasks.py gets the new task.`,
    );
  }
  const tasksPath = path.join(repo.packageDir, options.app, "tasks.py");
  if (!fs.existsSync(tasksPath)) {
    throw new GeneratorError(
      `${rel(repo, tasksPath)} does not exist. Tier 1 appends to an existing app's tasks.py ` +
        `— generate the app first (\`pnpm gen resource\`), or pass \`--app\` for the right one.`,
    );
  }

  const content = fs.readFileSync(tasksPath, "utf8");
  const importLine = `from keel.${options.app} import services`;
  if (!content.includes(importLine)) {
    throw new GeneratorError(
      `${rel(repo, tasksPath)} does not \`${importLine}\` — this generator only appends a ` +
        `delegation to an existing services import, it does not rewrite the file's imports. ` +
        `Add the import by hand and re-run.`,
    );
  }

  const functionName = `${names.resource}_task`;
  if (new RegExp(`^def ${functionName}\\b`, "m").test(content)) {
    throw new GeneratorError(
      `${rel(repo, tasksPath)} already defines \`${functionName}\`. This generator only ` +
        `appends; it cannot safely regenerate a fragment it already wrote into a file it ` +
        `does not own the whole of. Remove it by hand, or pick a different job name.`,
    );
  }

  const serviceName = options.service ?? names.resource;
  const block = [
    "",
    "",
    "@task",
    `def ${functionName}() -> None:`,
    `    """Fill in the parameters this task needs, then implement`,
    `    \`services.${serviceName}()\` to match — the mechanical half of a Tier-1 job stops`,
    `    at this one-line delegation (CLAUDE.md invariant 5)."""`,
    `    services.${serviceName}()`,
    "",
  ].join("\n");

  const plan = new Plan();
  plan.add(tasksPath, content.replace(/\n*$/, "") + block);

  if (options.dryRun) {
    reportPlan(repo, plan, true);
    console.log("\n--dry-run: nothing was written.");
    return 0;
  }

  plan.write();
  const formatted = formatPython(repo, [tasksPath]);
  if (!formatted.ok) plan.note(`  note: ${formatted.message}`);

  reportPlan(repo, plan, false);
  plan.note("");
  console.log(
    `\nNext, and not done for you:\n` +
      `  - implement \`services.${serviceName}\` in ` +
      `${rel(repo, path.join(repo.packageDir, options.app, "services.py"))}\n` +
      `  - give \`${functionName}\` the parameters it actually needs and pass them through ` +
      `\`.enqueue(...)\` at its call site\n` +
      `  - add view/create permission codes for this job's domain if it doesn't have them yet ` +
      `(\`pnpm gen permission\`), same as a resource.`,
  );

  if (!options.verify) {
    console.log("\n--no-verify: the DB-free gates were not run.");
    return 0;
  }
  const gates = runDbFreeGates(repo);
  return reportGates(gates) ? 0 : 1;
}

// --- Tier 2 -----------------------------------------------------------

const TEMPLATE_DIR = "job";

function renderStepFunctions(steps: string[]): string[] {
  const blocks = steps.map((name) => [
    `def _step_${name}(context: StepContext) -> None:`,
    "    return None",
  ]);
  const out: string[] = [];
  blocks.forEach((block, i) => {
    if (i > 0) out.push("", "");
    out.push(...block);
  });
  return out;
}

function renderStepSpecs(steps: string[]): string[] {
  return steps.map((name) => `            JobStepSpec(name="${name}", run=_step_${name}),`);
}

function renderStepUnitTests(steps: string[]): string[] {
  const blocks = steps.map((name) => [
    `def test__step_${name}_runs_against_a_step_context() -> None:`,
    '    context = StepContext(job_id="job", organization_id="org", params={}, results={})',
    `    _step_${name}(context)  # does not raise`,
  ]);
  const out: string[] = [];
  blocks.forEach((block, i) => {
    if (i > 0) out.push("", "");
    out.push(...block);
  });
  return out;
}

function generateTier2(repo: Repo, names: Names, options: JobOptions): number {
  const steps = parseSteps(options.steps);
  const jobsDir = path.join(repo.packageDir, "jobs");
  const targetFile = path.join(jobsDir, `${names.resource}.py`);
  const testFile = path.join(jobsDir, "tests", `test_${names.resource}.py`);
  const appsFile = path.join(jobsDir, "apps.py");

  if (fs.existsSync(targetFile) && !options.force) {
    throw new GeneratorError(
      `${rel(repo, targetFile)} already exists. Pass --force to overwrite it. Nothing was written.`,
    );
  }

  const templateDir = path.join(repo.templatesDir, TEMPLATE_DIR);
  if (!fs.existsSync(templateDir)) {
    throw new GeneratorError(`Templates not found at ${rel(repo, templateDir)}.`);
  }

  const stepImports = steps.map((name) => `_step_${name}`).join(", ");
  const inserts: Record<string, string[]> = {
    step_functions: renderStepFunctions(steps),
    step_specs: renderStepSpecs(steps),
    job_type_import: [
      `from keel.jobs.${names.resource} import __RESOURCE___JOB_TYPE, ${stepImports}`,
    ],
    // Trailing comma always, even for one step: `("sweep")` is just a
    // parenthesized string, not a tuple — ruff format strips the parens
    // entirely once it sees that, and `len(_STEP_NAMES)` silently becomes
    // the string's length instead of 1.
    step_names_tuple: [`_STEP_NAMES = (${steps.map((s) => `"${s}",`).join(" ")})`],
    step_unit_tests: renderStepUnitTests(steps),
  };

  const mainSource = fs.readFileSync(path.join(templateDir, "__resource__.py"), "utf8");
  const testSource = fs.readFileSync(
    path.join(templateDir, "tests", "test___resource__.py"),
    "utf8",
  );

  const plan = new Plan();
  plan.add(
    targetFile,
    render(mainSource, { names, flags: new Set(), inserts }, "templates/job/__resource__.py"),
  );
  plan.add(
    testFile,
    render(
      testSource,
      { names, flags: new Set(), inserts },
      "templates/job/tests/test___resource__.py",
    ),
  );

  const splice = spliceJobRegistration(
    appsFile,
    { module: names.resource, comment: names.resource },
    options.dryRun,
  );
  plan.splices.push(splice);

  if (options.dryRun) {
    reportPlan(repo, plan, true);
    console.log("\n--dry-run: nothing was written.");
    return 0;
  }

  plan.write();
  const formatted = formatPython(repo, [
    targetFile,
    testFile,
    ...(splice.changed ? [appsFile] : []),
  ]);
  if (!formatted.ok) plan.note(`  note: ${formatted.message}`);

  reportPlan(repo, plan, false);
  plan.note("");
  console.log(
    `\nNext, and not done for you:\n` +
      `  - fill in each step's real work in ${rel(repo, targetFile)} (every step is a stub` +
      ` returning None)\n` +
      `  - wire creation through \`keel.jobs.services\`'s job-creation service, not by hand\n` +
      `  - add view/create permission codes for this job's domain if it doesn't have them yet` +
      ` (\`pnpm gen permission\`)\n` +
      `  - if this job needs per-tenant concurrency limits or live progress, use` +
      ` \`keel/jobs/concurrency.py\` / \`keel/jobs/sse.py\` — neither is wired here.`,
  );

  if (!options.verify) {
    console.log("\n--no-verify: the DB-free gates were not run.");
    return 0;
  }
  const gates = runDbFreeGates(repo);
  return reportGates(gates) ? 0 : 1;
}
