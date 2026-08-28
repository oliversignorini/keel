/**
 * The write plan and the output contract (docs/plans/phase-19.md 19.A
 * "Output contract").
 *
 * "On success, print every file written and every anchor spliced, as an
 * explicit list. This is the single highest-value behaviour in the phase:
 * it means the calling agent never re-reads the tree to discover what
 * happened, and knows exactly which files are its to edit next."
 *
 * So the plan is built in full before a single byte is written — which is
 * also what makes `--dry-run` the same code path as a real run rather than
 * a second, drifting implementation of it.
 */

import * as fs from "node:fs";
import * as path from "node:path";

import type { Splice } from "./anchors.js";
import type { Repo } from "./repo.js";
import { rel } from "./repo.js";

export interface PlannedFile {
  absolutePath: string;
  contents: string;
  /** Set when a file is deliberately left alone (an existing migration). */
  skipReason?: string;
}

export class Plan {
  readonly files: PlannedFile[] = [];
  readonly splices: Splice[] = [];
  readonly notes: string[] = [];

  add(absolutePath: string, contents: string): void {
    this.files.push({ absolutePath, contents });
  }

  skip(absolutePath: string, reason: string): void {
    this.files.push({ absolutePath, contents: "", skipReason: reason });
  }

  note(message: string): void {
    this.notes.push(message);
  }

  write(): void {
    for (const file of this.files) {
      if (file.skipReason) continue;
      fs.mkdirSync(path.dirname(file.absolutePath), { recursive: true });
      fs.writeFileSync(file.absolutePath, file.contents, "utf8");
    }
  }
}

export function reportPlan(repo: Repo, plan: Plan, dryRun: boolean): void {
  const heading = dryRun ? "Would write" : "Wrote";
  const written = plan.files.filter((f) => !f.skipReason);
  const skipped = plan.files.filter((f) => f.skipReason);

  console.log(`\n${heading} ${written.length} file(s):`);
  for (const file of written) {
    console.log(`  ${rel(repo, file.absolutePath)}`);
  }

  if (skipped.length > 0) {
    console.log(`\nLeft alone:`);
    for (const file of skipped) {
      console.log(`  ${rel(repo, file.absolutePath)} — ${file.skipReason}`);
    }
  }

  if (plan.splices.length > 0) {
    console.log(`\n${dryRun ? "Would splice" : "Spliced"}:`);
    for (const splice of plan.splices) {
      const status = splice.changed ? "" : "  (already present, unchanged)";
      console.log(`  ${rel(repo, splice.file)}: ${splice.description}${status}`);
    }
  }

  if (plan.notes.length > 0) {
    console.log("");
    for (const note of plan.notes) console.log(note);
  }
}
