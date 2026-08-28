/**
 * Files the generator does not own, spliced rather than written
 * (docs/plans/phase-19.md 19.A "Files it does not own").
 *
 * The plan proposed anchor *comments* (`# keel:generated-apps — do not
 * remove`). This implements the same idea without them: each splice finds
 * its insertion point structurally — the last entry of the `INSTALLED_APPS`
 * list, the last `ninja_api.add_router(...)` call, the closing paren of
 * `_MEMBER_CODES` — because those four files carry no anchor comments today
 * and adding them is outside 19.A's path list. Structural location also
 * survives a user reordering the list, which an anchor comment does not.
 *
 * Every splice is idempotent: if the entry is already present the splice
 * is a no-op and reports itself as "already present". That is what lets
 * `apps/api/keel/widgets/` regenerate without perturbing the four files it
 * was hand-wired into years of commits ago.
 */

import * as fs from "node:fs";

export interface Splice {
  file: string;
  description: string;
  /** False when the entry was already there. */
  changed: boolean;
}

interface SpliceSpec {
  file: string;
  description: string;
  /** The exact line(s) to insert, already indented. */
  insert: string[];
  /** Detects an entry that is already present. */
  present: (content: string) => boolean;
  /** Returns the 0-based line index to insert *before*. */
  locate: (lines: string[]) => number;
}

export class AnchorError extends Error {}

function applySpec(spec: SpliceSpec, dryRun: boolean): Splice {
  if (!fs.existsSync(spec.file)) {
    throw new AnchorError(
      `Cannot splice ${spec.description}: ${spec.file} does not exist. ` +
        `The generator expects a Keel-shaped repository.`,
    );
  }
  const content = fs.readFileSync(spec.file, "utf8");
  if (spec.present(content)) {
    return { file: spec.file, description: spec.description, changed: false };
  }
  const lines = content.split("\n");
  const at = spec.locate(lines);
  if (at < 0) {
    throw new AnchorError(
      `Cannot splice ${spec.description}: could not locate the insertion point in ${spec.file}. ` +
        `The file has drifted from the shape this generator knows; add the entry by hand.`,
    );
  }
  lines.splice(at, 0, ...spec.insert);
  if (!dryRun) fs.writeFileSync(spec.file, lines.join("\n"), "utf8");
  return { file: spec.file, description: spec.description, changed: true };
}

/** Index of the last line matching `pattern`, or -1. */
function lastIndexMatching(lines: string[], pattern: RegExp): number {
  for (let i = lines.length - 1; i >= 0; i--) {
    if (pattern.test(lines[i]!)) return i;
  }
  return -1;
}

export interface SpliceTargets {
  settings: string;
  urls: string;
  permissions: string;
  roles: string;
  permissionTests: string;
}

export interface AppSpliceInput {
  pythonPackage: string;
  app: string;
}

/** `INSTALLED_APPS` in config/settings/base.py. */
export function spliceInstalledApps(
  targets: SpliceTargets,
  input: AppSpliceInput,
  dryRun: boolean,
): Splice {
  const entry = `    "${input.pythonPackage}.${input.app}",`;
  const appRe = new RegExp(`^\\s*"${input.pythonPackage}\\.[a-z_]+",\\s*$`);
  return applySpec(
    {
      file: targets.settings,
      description: `INSTALLED_APPS += "${input.pythonPackage}.${input.app}"`,
      insert: [entry],
      present: (content) => content.includes(`"${input.pythonPackage}.${input.app}"`),
      locate: (lines) => {
        const last = lastIndexMatching(lines, appRe);
        return last === -1 ? -1 : last + 1;
      },
    },
    dryRun,
  );
}

/** The router import and its `add_router` call in config/urls.py. */
export function spliceRouter(
  targets: SpliceTargets,
  input: AppSpliceInput,
  orgSegment: string,
  dryRun: boolean,
): Splice[] {
  const importLine = `from ${input.pythonPackage}.${input.app}.views import router as ${input.app}_router`;
  const addLine = `ninja_api.add_router("/${orgSegment}", ${input.app}_router)`;
  const importRe = new RegExp(`^from ${input.pythonPackage}\\.[a-z_.]+ import `);
  const addRe = /^ninja_api\.add_router\(/;

  const importSplice = applySpec(
    {
      file: targets.urls,
      description: `config/urls.py imports ${input.app}_router`,
      insert: [importLine],
      present: (content) => content.includes(importLine),
      locate: (lines) => {
        const last = lastIndexMatching(lines, importRe);
        return last === -1 ? -1 : last + 1;
      },
    },
    dryRun,
  );

  const addSplice = applySpec(
    {
      file: targets.urls,
      description: `config/urls.py mounts ${input.app}_router on /${orgSegment}`,
      insert: [addLine],
      present: (content) => content.includes(addLine),
      locate: (lines) => {
        const last = lastIndexMatching(lines, addRe);
        return last === -1 ? -1 : last + 1;
      },
    },
    dryRun,
  );

  return [importSplice, addSplice];
}

export interface PermissionSpliceInput {
  /** `INVOICE_VIEW` */
  constant: string;
  /** `invoice.view` */
  code: string;
}

/**
 * One permission code, spliced into the four places a code has to appear
 * to be real: its `Perm` constant, its `registry.register(...)`, a preset
 * role that grants it, and the guard test table the invariant-2 meta-test
 * walks. Registering a code and stopping is what produces a permission
 * nobody's role holds and no test covers — which the meta-tests then fail
 * on, after the generator has already claimed success.
 */
export function splicePermission(
  targets: SpliceTargets,
  input: PermissionSpliceInput,
  dryRun: boolean,
): Splice[] {
  const splices: Splice[] = [];

  splices.push(
    applySpec(
      {
        file: targets.permissions,
        description: `Perm.${input.constant} = "${input.code}"`,
        insert: [`    ${input.constant} = "${input.code}"`],
        present: (content) => new RegExp(`^\\s*${input.constant}\\s*=`, "m").test(content),
        locate: (lines) => {
          const last = lastIndexMatching(
            lines,
            /^\s{4}[A-Z][A-Z0-9_]*\s*=\s*"[a-z_]+\.[a-z_]+"\s*$/,
          );
          return last === -1 ? -1 : last + 1;
        },
      },
      dryRun,
    ),
  );

  splices.push(
    applySpec(
      {
        file: targets.permissions,
        description: `registry.register(Perm.${input.constant}, _role_guard(...))`,
        insert: [`registry.register(Perm.${input.constant}, _role_guard(Perm.${input.constant}))`],
        present: (content) => content.includes(`registry.register(Perm.${input.constant},`),
        locate: (lines) => {
          const last = lastIndexMatching(lines, /^registry\.register\(/);
          return last === -1 ? -1 : last + 1;
        },
      },
      dryRun,
    ),
  );

  splices.push(
    applySpec(
      {
        file: targets.roles,
        description: `roles.py _MEMBER_CODES += Perm.${input.constant}`,
        insert: [`    Perm.${input.constant},`],
        present: (content) =>
          new RegExp(`_MEMBER_CODES[\\s\\S]*?\\n\\}`, "m")
            .exec(content)?.[0]
            ?.includes(`Perm.${input.constant},`) ?? false,
        locate: (lines) => {
          const start = lines.findIndex((line) => /^_MEMBER_CODES\s*=\s*\{/.test(line));
          if (start === -1) return -1;
          for (let i = start; i < lines.length; i++) {
            if (/^\}\s*$/.test(lines[i]!)) return i;
          }
          return -1;
        },
      },
      dryRun,
    ),
  );

  splices.push(
    applySpec(
      {
        file: targets.permissionTests,
        description: `test_permissions.py role-only guard table += Perm.${input.constant}`,
        insert: [`    Perm.${input.constant},`],
        present: (content) => {
          const block = /for _code in \(([\s\S]*?)\n\):/.exec(content)?.[1];
          return block?.includes(`Perm.${input.constant},`) ?? false;
        },
        locate: (lines) => {
          const start = lines.findIndex((line) => /^for _code in \(\s*$/.test(line));
          if (start === -1) return -1;
          for (let i = start; i < lines.length; i++) {
            if (/^\):\s*$/.test(lines[i]!)) return i;
          }
          return -1;
        },
      },
      dryRun,
    ),
  );

  return splices;
}

export interface JobRegistrationInput {
  /** The module under `keel/jobs/` to import, e.g. `invoice_rollup`. */
  module: string;
  /** Text for the trailing `# noqa: F401 — registers the ... job type` comment. */
  comment: string;
}

/**
 * The import inside `JobsConfig.ready()` that registers a Tier-2 job
 * type (`gen job --tier 2`, docs/plans/phase-19.md 19.B) — mirrors how
 * `keel/jobs/demo.py` is registered. A job module that is never imported
 * is a job type nothing ever registers, which fails loudly the first time
 * something tries to create a job of that type rather than at generation
 * time, so this splice exists for the same reason the other four do.
 *
 * Not `applySpec`: after a second `gen job --tier 2` run, `formatPython`'s
 * `ruff check --select I --fix` merges the two separate
 * `from keel.jobs import X` lines it finds into one parenthesized
 * `from keel.jobs import (\n    X,\n    Y,\n)` group — a shape `applySpec`'s
 * single fixed `insert` can't both detect (`present`) and correctly extend
 * (`locate`, which would need to insert *inside* the group at a different
 * indent than a standalone line needs). This splices around that shape
 * explicitly instead.
 */
export function spliceJobRegistration(
  appsFile: string,
  input: JobRegistrationInput,
  dryRun: boolean,
): Splice {
  if (!fs.existsSync(appsFile)) {
    throw new AnchorError(
      `Cannot register the ${input.module} job type: ${appsFile} does not exist. ` +
        `The generator expects a Keel-shaped repository.`,
    );
  }
  const description = `keel/jobs/apps.py ready() imports keel.jobs.${input.module}`;
  const content = fs.readFileSync(appsFile, "utf8");

  // Bounded lookahead, not an unbounded scan: `ready()` is a handful of
  // lines, and bounding this keeps a coincidentally-matching module name
  // elsewhere in the file (there shouldn't be one, but this is a splice
  // into a file the generator does not fully own) from producing a false
  // "already present".
  const alreadyPresent = new RegExp(
    `from keel\\.jobs import\\b[\\s\\S]{0,800}?\\b${input.module}\\b`,
  ).test(content);
  if (alreadyPresent) {
    return { file: appsFile, description, changed: false };
  }

  const lines = content.split("\n");
  const groupStart = lines.findIndex((line) => /^\s{8}from keel\.jobs import \(\s*$/.test(line));

  let at = -1;
  let insert: string[];
  if (groupStart !== -1) {
    let closeIdx = -1;
    for (let i = groupStart + 1; i < lines.length; i++) {
      if (/^\s{8}\)\s*$/.test(lines[i]!)) {
        closeIdx = i;
        break;
      }
    }
    if (closeIdx === -1) {
      throw new AnchorError(
        `Cannot register the ${input.module} job type: unterminated ` +
          `"from keel.jobs import (" group in ${appsFile}.`,
      );
    }
    at = closeIdx;
    insert = [
      `            ${input.module},  # noqa: F401 — registers the ${input.comment} job type`,
    ];
  } else {
    const last = lastIndexMatching(
      lines,
      /^\s{8}from keel\.jobs import [a-zA-Z_][a-zA-Z0-9_]*\s*(#.*)?$/,
    );
    if (last !== -1) {
      at = last + 1;
    } else {
      const readyIdx = lines.findIndex((line) => /^\s{4}def ready\(self\) -> None:\s*$/.test(line));
      if (readyIdx === -1) {
        throw new AnchorError(
          `Cannot register the ${input.module} job type: could not find ` +
            `"def ready(self) -> None:" in ${appsFile}.`,
        );
      }
      at = readyIdx + 1;
    }
    insert = [
      `        from keel.jobs import ${input.module}  # noqa: F401 — registers the ${input.comment} job type`,
    ];
  }

  lines.splice(at, 0, ...insert);
  if (!dryRun) fs.writeFileSync(appsFile, lines.join("\n"), "utf8");
  return { file: appsFile, description, changed: true };
}
