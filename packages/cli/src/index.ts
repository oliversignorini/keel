#!/usr/bin/env node
/**
 * `pnpm gen <generator>` — Keel's code generators (ADR 0004, "Generators,
 * not prompts, are Keel's capability surface").
 *
 * This CLI ships with the template and is renamed alongside everything
 * else by `scripts/init.ts`. It is a product feature of the project, not
 * authoring scaffolding: a template whose invariants are enforceable only
 * by a model reading CLAUDE.md is weaker than one with a generator that
 * cannot emit a non-conforming slice.
 *
 * `--help` is the whole discovery mechanism, deliberately — ADR 0004
 * rejects a second, machine-readable catalogue alongside it on the grounds
 * that the copy read less often is the copy that goes stale.
 */

import { generateE2e } from "./generators/e2e.js";
import { generateEmail } from "./generators/email.js";
import { generateJob } from "./generators/job.js";
import { generatePermission } from "./generators/permission.js";
import { generateResource } from "./generators/resource.js";
import { syncClient } from "./generators/sync-client.js";

const HELP = `
gen — generate a conforming vertical slice.

Usage:
  pnpm gen <generator> [args] [flags]

Generators:
  resource <Name>            A full CRUD vertical slice: model, migration,
                             selectors, services, schemas, views, tasks,
                             admin, factory and tests — plus the four CRUD
                             permission codes, wired into INSTALLED_APPS
                             and the org-scoped router.
  readonly-resource <Name>   The same, minus the write paths: list and
                             retrieve only, no mutating services, no write
                             schemas, one permission code.
  permission <code>          One permission code (e.g. invoice.export),
                             spliced into all four places it has to exist:
                             the Perm constant, its guard registration, a
                             preset role, and the guard test table.
  sync-client                Regenerate openapi.merged.json and the
                             TypeScript client. The only generator that
                             touches them, and it takes a lock in the
                             shared .git directory so two worktrees cannot.
  email <Name>                A transactional email: the react-email
                             template (props, {{TOKEN}} defaults, and a
                             button + fallback link for a URL token) and
                             the Python sender in keel/notifications/
                             emails.py. The body copy and the call site
                             (a Tier-1 task on transaction.on_commit())
                             are judgement, left as a TODO.
  job <Name>                 A job type. --tier 1 appends one @task
                             delegation to an existing app's tasks.py.
                             --tier 2 emits a keel/jobs/<name>.py module
                             (steps, registration) plus tests, following
                             keel/jobs/demo.py's shape. --tier is required
                             — this generator does not guess it.
  e2e <Resource>              Not a scaffolder: writes a Playwright spec
                             for the happy CRUD path against the --ui
                             pages, then runs the full /check-invariants
                             suite including pytest. The ship gate — run
                             it when the feature is finished.

Flags for resource / readonly-resource:
  --fields <spec>   Comma-separated name:type list. Types: str, str(N),
                    text, int, decimal, bool, date, datetime,
                    choice(a,b,c), fk(<app>.<Model>). A trailing "?" makes
                    the field optional, e.g. "note:text?".
                    Everything past this — constraints, indexes, Meta,
                    validators — is judgement and is left to a marked
                    insertion point in models.py.
  --ui / --no-ui    Generate the frontend pages: a list, create and detail
                    route under apps/web/app/(app)/app/[org]/<resources>/,
                    assembled from @keel/ui's data-table/resource-form/
                    form-field/empty-state/page-header primitives, plus a
                    thin apps/web/lib/<resources>/api.ts wrapper around the
                    generated client. Not supported on readonly-resource yet.
  --permissions <crud|manage>
                    crud (default) emits <resource>.view/.create/.update/
                    .delete. manage emits the coarser
                    <resources>.view/.manage pair.
  --force           Overwrite an existing app directory. A committed
                    migration is still never regenerated.
  --dry-run         Print the file plan and the splices, write nothing.
  --no-verify       Skip the DB-free gates (makemigrations --check,
                    lint-imports, check_permission_lint.py) that otherwise
                    run after writing and decide the exit code.

Flags for sync-client:
  --dry-run         Print the steps, run nothing.
  --force           Break a lock left behind by a crashed run.

Flags for email:
  --subject <text>  Required. The email's subject line, and the default
                    <Layout preview/heading>.
  --tokens <spec>   Comma-separated UPPER_SNAKE placeholder names, e.g.
                    "ORGANIZATION_NAME,ACCEPT_URL". Defaults to a single
                    ACTION_URL token. A token ending in _URL gets a button
                    and a plain-text fallback link; every token becomes a
                    template prop and a keyword arg on the Python sender.
  --force           Overwrite an existing template file / append another
                    sender of the same name.
  --dry-run         Print the file plan, write nothing.

Flags for job:
  --tier <1|2>      Required. 1: fire-and-forget, needs --app. 2:
                    multi-step, resumable.
  --app <app>       Tier 1 only: the existing app whose tasks.py gets the
                    new task.
  --service <name>  Tier 1 only: the services.py function to delegate to.
                    Defaults to the job's own name.
  --steps <names>   Tier 2 only: comma-separated step names, e.g.
                    "fetch,transform,publish". Defaults to one "run" step.
  --force           Tier 2 only: overwrite an existing job module.
  --dry-run         Print the file plan and the splice, write nothing.
  --no-verify       Skip the DB-free gates.

Flags for e2e:
  --fields <spec>   Same DSL as resource, used only to pick which field the
                    spec fills in and asserts on. Defaults to "name".
  --force           Overwrite an existing spec file.
  --dry-run         Print the file plan, write nothing, and skip the gate
                    suite.

Examples:
  pnpm gen resource Invoice --fields "number:str(32),amount:decimal,due_on:date,note:text?"
  pnpm gen readonly-resource AuditExport --fields "requested_for:date"
  pnpm gen permission invoice.export
  pnpm gen sync-client
  pnpm gen email InvoiceOverdue --subject "Your invoice is overdue" --tokens "ORGANIZATION_NAME,INVOICE_URL"
  pnpm gen job SendInvoiceReminder --tier 1 --app invoices
  pnpm gen job RollupMonthlyUsage --tier 2 --steps "fetch,aggregate,publish"
  pnpm gen e2e Invoice --fields "number:str(32)"
`;

interface ParsedArgs {
  generator?: string;
  positional: string[];
  flags: Map<string, string | boolean>;
}

function parseArgs(argv: string[]): ParsedArgs {
  const positional: string[] = [];
  const flags = new Map<string, string | boolean>();
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]!;
    if (!arg.startsWith("--")) {
      positional.push(arg);
      continue;
    }
    const key = arg.slice(2);
    const eq = key.indexOf("=");
    if (eq !== -1) {
      flags.set(key.slice(0, eq), key.slice(eq + 1));
      continue;
    }
    const next = argv[i + 1];
    if (next !== undefined && !next.startsWith("--")) {
      flags.set(key, next);
      i += 1;
    } else {
      flags.set(key, true);
    }
  }
  return { generator: positional[0], positional: positional.slice(1), flags };
}

function requireName(positional: string[], generator: string): string {
  const name = positional[0];
  if (!name) {
    throw new Error(`\`gen ${generator}\` needs a name, e.g. \`pnpm gen ${generator} Invoice\`.`);
  }
  return name;
}

function stringFlag(flags: Map<string, string | boolean>, key: string): string | undefined {
  const value = flags.get(key);
  if (value === undefined) return undefined;
  if (value === true) throw new Error(`--${key} needs a value.`);
  return value as string;
}

function permissionScheme(flags: Map<string, string | boolean>): "crud" | "manage" {
  const raw = stringFlag(flags, "permissions") ?? "crud";
  if (raw !== "crud" && raw !== "manage") {
    throw new Error(`--permissions must be "crud" or "manage" (got "${raw}").`);
  }
  return raw;
}

function main(): number {
  const { generator, positional, flags } = parseArgs(process.argv.slice(2));

  if (!generator || flags.has("help") || generator === "help") {
    console.log(HELP.trim());
    return generator ? 0 : 1;
  }

  const dryRun = flags.get("dry-run") === true;
  const force = flags.get("force") === true;
  const verify = flags.get("no-verify") !== true;

  switch (generator) {
    case "resource":
    case "readonly-resource":
      return generateResource({
        name: requireName(positional, generator),
        fields: stringFlag(flags, "fields"),
        ui: flags.get("ui") === true,
        dryRun,
        force,
        verify,
        readonly: generator === "readonly-resource",
        permissionScheme: permissionScheme(flags),
      });
    case "permission": {
      const code = positional[0];
      if (!code) {
        throw new Error(
          "`gen permission` needs a code, e.g. `pnpm gen permission invoice.export`.",
        );
      }
      return generatePermission({ code, dryRun });
    }
    case "sync-client":
      return syncClient({ dryRun, force });
    case "email":
      return generateEmail({
        name: requireName(positional, generator),
        subject: stringFlag(flags, "subject"),
        tokens: stringFlag(flags, "tokens"),
        dryRun,
        force,
      });
    case "job": {
      const tierRaw = stringFlag(flags, "tier");
      if (tierRaw !== "1" && tierRaw !== "2") {
        throw new Error(`\`gen job\` needs --tier 1 or --tier 2 (got ${tierRaw ?? "nothing"}).`);
      }
      return generateJob({
        name: requireName(positional, generator),
        tier: tierRaw === "1" ? 1 : 2,
        steps: stringFlag(flags, "steps"),
        app: stringFlag(flags, "app"),
        service: stringFlag(flags, "service"),
        dryRun,
        force,
        verify,
      });
    }
    case "e2e":
      return generateE2e({
        name: requireName(positional, generator),
        fields: stringFlag(flags, "fields"),
        dryRun,
        force,
      });
    default:
      console.error(`Unknown generator "${generator}".\n`);
      console.log(HELP.trim());
      return 1;
  }
}

try {
  process.exit(main());
} catch (error) {
  console.error(`gen: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
}
