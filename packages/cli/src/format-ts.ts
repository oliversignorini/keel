/**
 * Post-generation `prettier --write` for `--ui` output (19.C), the same
 * reason `format.ts` runs `ruff format` on generated Python: a template
 * can't choose line breaks that fit every resource name, and the repo's
 * own `pnpm lint` runs `prettier --check .` over everything including
 * generated files.
 */

import { spawnSync } from "node:child_process";
import * as path from "node:path";

import type { Repo } from "./repo.js";

export interface FormatResult {
  ok: boolean;
  message: string;
}

export function formatTs(repo: Repo, absolutePaths: string[]): FormatResult {
  if (absolutePaths.length === 0) return { ok: true, message: "" };
  // Invoke prettier's own JS entrypoint with `process.execPath`, not the
  // `.bin/prettier` shim: on Windows that shim is a `.cmd` batch file, and
  // running one via `spawnSync` needs `shell: true` — which re-tokenizes
  // the command line and mangles any argument containing a space (this
  // repo routinely sits under a directory with one in its name, the same
  // trap format.ts's `ruff` note and `scripts/init.ts` both document).
  // `node <cli.js>` is a real executable either way, so no shell is needed.
  const cli = path.join(repo.root, "node_modules", "prettier", "bin", "prettier.cjs");
  const result = spawnSync(process.execPath, [cli, "--write", ...absolutePaths], {
    cwd: repo.root,
    encoding: "utf8",
  });
  if (result.error) {
    return {
      ok: false,
      message:
        `could not run prettier (${result.error.message}) — the generated frontend files ` +
        `are written but unformatted, and \`prettier --check .\` will fail until you run it ` +
        `yourself.`,
    };
  }
  if (result.status !== 0) {
    return {
      ok: false,
      message: `\`prettier --write\` failed: ${`${result.stderr ?? ""}${result.stdout ?? ""}`.trim()}`,
    };
  }
  return { ok: true, message: "" };
}
