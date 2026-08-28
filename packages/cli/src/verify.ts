/**
 * The DB-free gates (docs/plans/phase-19.md 19.A "Verification").
 *
 * "After writing, run the DB-free gates and exit non-zero on failure:
 * makemigrations --check --dry-run, uv run lint-imports,
 * scripts/check_permission_lint.py. Nothing that needs Postgres — the
 * generator must work in a worktree where `docker compose up` has never
 * been run."
 *
 * `makemigrations` is run first and for real (not --check) when the app is
 * brand new, because a generated app with no migration cannot pass
 * `--check` and cannot be imported by the test suite either. An existing
 * migration is never regenerated — invariant 4 is one baseline migration
 * per app, and rewriting a committed one is a schema edit wearing a
 * generator's clothes.
 */

import { spawnSync } from "node:child_process";

import type { Repo } from "./repo.js";

export interface GateResult {
  name: string;
  command: string;
  ok: boolean;
  output: string;
}

function runUv(repo: Repo, args: string[]): { ok: boolean; output: string } {
  // Deliberately not `shell: true` — see the note in format.ts::ruff.
  const result = spawnSync("uv", args, {
    cwd: repo.apiDir,
    encoding: "utf8",
  });
  if (result.error) {
    return { ok: false, output: `could not run "uv ${args.join(" ")}": ${result.error.message}` };
  }
  return {
    ok: result.status === 0,
    output: `${result.stdout ?? ""}${result.stderr ?? ""}`.trim(),
  };
}

/** Produces `<app>/migrations/0001_initial.py`. No database required. */
export function makeMigrations(repo: Repo, app: string): GateResult {
  const args = ["run", "python", "manage.py", "makemigrations", app];
  const { ok, output } = runUv(repo, args);
  return { name: `makemigrations ${app}`, command: `uv ${args.join(" ")}`, ok, output };
}

export function runDbFreeGates(repo: Repo): GateResult[] {
  const gates: GateResult[] = [];

  {
    const args = ["run", "python", "manage.py", "makemigrations", "--check", "--dry-run"];
    const { ok, output } = runUv(repo, args);
    gates.push({
      name: "invariant 4 — schema changes are migrations",
      command: `uv ${args.join(" ")}`,
      ok,
      output,
    });
  }

  {
    const args = ["run", "lint-imports"];
    const { ok, output } = runUv(repo, args);
    gates.push({
      name: "invariant 1 — domain purity",
      command: `uv ${args.join(" ")}`,
      ok,
      output,
    });
  }

  {
    const args = ["run", "python", "../../scripts/check_permission_lint.py"];
    const { ok, output } = runUv(repo, args);
    gates.push({
      name: "invariant 2 — permission placement",
      command: `uv ${args.join(" ")}`,
      ok,
      output,
    });
  }

  return gates;
}

export function reportGates(gates: GateResult[]): boolean {
  console.log("\nDB-free gates:");
  let allOk = true;
  for (const gate of gates) {
    console.log(`  ${gate.ok ? "PASS" : "FAIL"}  ${gate.name}  (${gate.command})`);
    if (!gate.ok) {
      allOk = false;
      for (const line of gate.output.split("\n")) {
        if (line.trim()) console.log(`        ${line}`);
      }
    }
  }
  return allOk;
}
