/**
 * `gen permission <resource.action>`.
 *
 * A permission code is not one line, it is four, and a code that has only
 * some of them is broken in a way the meta-tests catch loudly and late:
 *
 *   Perm.<CONST>                    the vocabulary
 *   registry.register(...)          the guard behind it
 *   roles.py _MEMBER_CODES          a preset that actually grants it
 *   test_permissions.py             the allow/deny pair invariant 2 wants
 *
 * All four live in files this generator does not own, so all four are
 * idempotent splices (see anchors.ts). Registering a code and stopping —
 * the failure mode of writing this by hand — produces a permission nobody
 * holds and no test covers.
 *
 * The guard is always role-only. A subject-aware guard is judgement, and
 * `templates/permission/subject_guard.py` is the shape to copy when the
 * rule genuinely depends on the object rather than the actor's role.
 */

import { splicePermission } from "../anchors.js";
import { formatPython } from "../format.js";
import { Plan, reportPlan } from "../plan.js";
import { loadRepo, rel, spliceTargets } from "../repo.js";

export interface PermissionOptions {
  /** `invoice.export` */
  code: string;
  dryRun: boolean;
}

export class InvalidPermissionCode extends Error {}

export function constantFor(code: string): string {
  if (!/^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/.test(code)) {
    throw new InvalidPermissionCode(
      `Permission code "${code}" must be <resource>.<action>, lowercase snake_case on ` +
        `both sides — e.g. invoice.export. It becomes a Perm constant and a string ` +
        `stored in every Role row.`,
    );
  }
  return code.replace(".", "_").toUpperCase();
}

export function generatePermission(options: PermissionOptions): number {
  const repo = loadRepo();
  const constant = constantFor(options.code);
  const targets = spliceTargets(repo);

  const plan = new Plan();
  plan.splices.push(...splicePermission(targets, { constant, code: options.code }, options.dryRun));

  if (options.dryRun) {
    reportPlan(repo, plan, true);
    console.log("\n--dry-run: nothing was written.");
    return 0;
  }

  const touched = [...new Set(plan.splices.filter((s) => s.changed).map((s) => s.file))];
  const formatted = formatPython(repo, touched);
  if (!formatted.ok) plan.note(`  note: ${formatted.message}`);

  reportPlan(repo, plan, false);

  if (plan.splices.every((s) => !s.changed)) {
    console.log(`\nPerm.${constant} was already fully wired — nothing to do.`);
    return 0;
  }

  console.log(
    `\nNext, and not done for you:\n` +
      `  - if this code's rule depends on the object and not just the actor's role, ` +
      `replace the generated \`_role_guard(Perm.${constant})\` registration in ` +
      `${rel(repo, targets.permissions)} with a subject-aware guard — ` +
      `templates/permission/subject_guard.py is the shape.\n` +
      `  - wire it onto the route(s) that need it.`,
  );
  return 0;
}
