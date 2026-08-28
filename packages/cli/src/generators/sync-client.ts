/**
 * `gen sync-client` — the five steps of `.claude/commands/sync-client.md`
 * as code (docs/plans/phase-19.md 19.A).
 *
 * This is the only generator that touches `openapi.merged.json` or
 * `packages/api-client/src/generated`, and `docs/review-2026-08.md` rule 3
 * allows exactly one worktree at a time to write them — two produces a
 * merge conflict in generated output that nobody can resolve by reading
 * it. That rule existed only in Markdown; the lock below makes it
 * something the machine enforces.
 *
 * The lock lives in the *shared* git directory, not in the worktree:
 * `git worktree` gives every worktree its own `.git` file pointing into
 * the main repository's `.git/worktrees/<name>`, so a lock placed in the
 * worktree would be invisible to the sibling worktree it exists to
 * exclude. `git rev-parse --git-common-dir` is the one thing that answers
 * "the directory all of these share" correctly from inside any of them.
 */

import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

import type { Repo } from "../repo.js";
import { loadRepo, rel } from "../repo.js";

export interface SyncClientOptions {
  dryRun: boolean;
  /** Break a lock left behind by a crashed run. */
  force: boolean;
}

const LOCK_NAME = "keel-gen-sync-client.lock";

interface LockContents {
  pid: number;
  worktree: string;
  startedAt: string;
}

export function gitCommonDir(repo: Repo): string {
  const result = spawnSync("git", ["rev-parse", "--git-common-dir"], {
    cwd: repo.root,
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error(
      `Could not locate the shared git directory (git rev-parse --git-common-dir): ` +
        `${(result.stderr ?? "").trim()}`,
    );
  }
  const dir = (result.stdout ?? "").trim();
  return path.isAbsolute(dir) ? dir : path.join(repo.root, dir);
}

export function lockPath(repo: Repo): string {
  return path.join(gitCommonDir(repo), LOCK_NAME);
}

/** Returns the holder when the lock is taken, or null when it was acquired. */
export function acquireLock(repo: Repo, force: boolean): LockContents | null {
  const file = lockPath(repo);
  const contents: LockContents = {
    pid: process.pid,
    worktree: repo.root,
    startedAt: new Date().toISOString(),
  };
  if (force && fs.existsSync(file)) fs.rmSync(file);
  try {
    // "wx" is the whole mechanism: an atomic create-or-fail, which is what
    // makes this a lock rather than a check followed by a race.
    fs.writeFileSync(file, JSON.stringify(contents, null, 2) + "\n", { flag: "wx" });
    return null;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
    try {
      return JSON.parse(fs.readFileSync(file, "utf8")) as LockContents;
    } catch {
      return { pid: -1, worktree: "<unreadable lock file>", startedAt: "" };
    }
  }
}

export function releaseLock(repo: Repo): void {
  const file = lockPath(repo);
  if (fs.existsSync(file)) fs.rmSync(file);
}

interface Step {
  label: string;
  command: string;
  args: string[];
  cwd: string;
}

function steps(repo: Repo): Step[] {
  return [
    {
      label: "merge the DRF and allauth specs into openapi.merged.json",
      command: "uv",
      args: ["run", "python", "../../scripts/merge_openapi.py"],
      cwd: repo.apiDir,
    },
    {
      label: "run orval over the merged spec",
      command: "pnpm",
      args: ["--filter", `@${repo.pythonPackage}/api-client`, "generate"],
      cwd: repo.root,
    },
    {
      label: "typecheck the generated client",
      command: "pnpm",
      args: ["--filter", `@${repo.pythonPackage}/api-client`, "typecheck"],
      cwd: repo.root,
    },
    {
      label: "typecheck the web app against the new types",
      command: "pnpm",
      args: ["--filter", "web", "typecheck"],
      cwd: repo.root,
    },
  ];
}

function changedPaths(repo: Repo): string[] {
  const result = spawnSync(
    "git",
    ["diff", "--name-only", "--", "openapi.merged.json", "packages/api-client/src/generated"],
    { cwd: repo.root, encoding: "utf8" },
  );
  return (result.stdout ?? "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function syncClient(options: SyncClientOptions): number {
  const repo = loadRepo();
  const plannedSteps = steps(repo);

  if (options.dryRun) {
    console.log(`Would take the lock at ${rel(repo, lockPath(repo))}, then run:`);
    for (const step of plannedSteps) {
      console.log(`  ${step.command} ${step.args.join(" ")}  (cwd: ${rel(repo, step.cwd) || "."})`);
    }
    console.log(
      `\nThen report which of openapi.merged.json / packages/api-client/src/generated changed.`,
    );
    console.log("\n--dry-run: nothing was written.");
    return 0;
  }

  const holder = acquireLock(repo, options.force);
  if (holder) {
    console.error(
      `Refusing to run: another worktree holds the sync-client lock.\n` +
        `  lock:     ${lockPath(repo)}\n` +
        `  held by:  ${holder.worktree} (pid ${holder.pid})\n` +
        `  since:    ${holder.startedAt}\n\n` +
        `Only one worktree at a time may regenerate openapi.merged.json or ` +
        `packages/api-client/src/generated — two produces a merge conflict in generated ` +
        `output that cannot be resolved by reading it. Wait for that run to finish, or ` +
        `pass --force if you are certain it crashed and left the lock behind.`,
    );
    return 1;
  }

  try {
    for (const step of plannedSteps) {
      console.log(`\n$ ${step.command} ${step.args.join(" ")}`);
      const result = spawnSync(step.command, step.args, {
        cwd: step.cwd,
        stdio: "inherit",
        shell: process.platform === "win32",
      });
      if (result.status !== 0) {
        console.error(`\nFAILED while trying to ${step.label}.`);
        return 1;
      }
    }
  } finally {
    releaseLock(repo);
  }

  const changed = changedPaths(repo);
  if (changed.length === 0) {
    console.log(
      `\nThe client was already in sync — openapi.merged.json and ` +
        `packages/api-client/src/generated are unchanged. Nothing to commit.`,
    );
    return 0;
  }
  console.log(`\nChanged, and needs committing:`);
  for (const file of changed) console.log(`  ${file}`);
  console.log(
    `\nCI's api-client-generation and contracts jobs both fail on drift here, so commit ` +
      `these alongside the change that caused them.`,
  );
  return 0;
}
