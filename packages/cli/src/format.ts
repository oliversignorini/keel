/**
 * Post-generation `ruff format`.
 *
 * Not a nicety. A template cannot choose its own line breaks: whether
 * `@router.get("/{org_slug}/invoices/", response=Page[InvoiceOut],
 * operation_id="listInvoices")` fits in 100 columns depends on how long
 * the resource is named, so any fixed choice in the template produces
 * output that fails `ruff format --check` for some names. Formatting the
 * render is the only way the generator can promise output that passes the
 * repo's own lint gate for every input — and it is what `scripts/init.ts`
 * already does after its own rewrite, for the same reason.
 */

import { spawnSync } from "node:child_process";

import type { Repo } from "./repo.js";

export interface FormatResult {
  ok: boolean;
  message: string;
}

function ruff(repo: Repo, args: string[]): { ok: boolean; error?: string; stderr: string } {
  const result = spawnSync("uv", ["run", "ruff", ...args], {
    cwd: repo.apiDir,
    encoding: "utf8",
    shell: process.platform === "win32",
  });
  if (result.error) return { ok: false, error: result.error.message, stderr: "" };
  return { ok: result.status === 0, stderr: (result.stderr ?? "").trim() };
}

export function formatPython(repo: Repo, paths: string[]): FormatResult {
  if (paths.length === 0) return { ok: true, message: "" };

  // Import *order* first, then layout. Which block `keel.<app>` sorts into
  // depends on the app's name relative to the other `keel.*` imports —
  // `keel.audits` sorts before `keel.core`, `keel.widgets` after — so a
  // template cannot state it correctly for every resource, and ruff's own
  // isort is the only thing that can. `--select I` restricts the fix to
  // exactly that: nothing else in the generated files gets silently
  // rewritten on the way out.
  const sorted = ruff(repo, ["check", "--select", "I", "--fix", "--quiet", ...paths]);
  if (sorted.error) {
    return {
      ok: false,
      message:
        `could not run \`uv run ruff\` (${sorted.error}) — the generated files are ` +
        `written but unsorted and unformatted, and \`ruff check\`/\`ruff format --check\` ` +
        `will fail until you run them yourself.`,
    };
  }
  if (!sorted.ok) {
    return { ok: false, message: `\`ruff check --select I --fix\` failed: ${sorted.stderr}` };
  }

  const formatted = ruff(repo, ["format", "--quiet", ...paths]);
  if (formatted.error) {
    return {
      ok: false,
      message:
        `could not run \`uv run ruff format\` (${formatted.error}) — the generated files ` +
        `are written but unformatted.`,
    };
  }
  if (!formatted.ok) {
    return { ok: false, message: `\`ruff format\` failed: ${formatted.stderr}` };
  }
  return { ok: true, message: "" };
}
