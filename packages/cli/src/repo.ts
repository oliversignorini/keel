/**
 * Where things are. Everything the generators touch is located from the
 * repo root rather than hard-coded relative to `import.meta.url`, so the
 * CLI works the same from `pnpm gen` at the root, from a subdirectory, and
 * from the disposable CI checkout.
 *
 * `pythonPackage` and `tenantSegment` are read from the repo, not assumed
 * to be "keel" and "orgs": `scripts/init.ts` renames both, and this CLI
 * ships to the instantiated project (ADR 0004, "The CLI ships"). A
 * generator that hard-codes "keel" is a generator that stops working the
 * moment the template is used for its actual purpose.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

export interface Repo {
  root: string;
  apiDir: string;
  /** `apps/api/<pythonPackage>` — where the Django apps live. */
  packageDir: string;
  pythonPackage: string;
  templatesDir: string;
  /** The URL segment org-scoped routers mount under. `orgs` */
  tenantSegment: string;
}

export class RepoNotFound extends Error {}

function looksLikeRepoRoot(dir: string): boolean {
  return (
    fs.existsSync(path.join(dir, "pnpm-workspace.yaml")) &&
    fs.existsSync(path.join(dir, "apps", "api", "manage.py"))
  );
}

export function findRepoRoot(startAt?: string): string {
  const starts = [startAt ?? process.cwd(), path.dirname(fileURLToPath(import.meta.url))];
  for (const start of starts) {
    let dir = path.resolve(start);
    for (;;) {
      if (looksLikeRepoRoot(dir)) return dir;
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  throw new RepoNotFound(
    "Could not find the repository root (looked for pnpm-workspace.yaml alongside " +
      "apps/api/manage.py). Run this from inside the project.",
  );
}

/** The single Python package under apps/api that holds the Django apps. */
function detectPythonPackage(apiDir: string): string {
  const candidates = fs
    .readdirSync(apiDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .filter((name) => name !== "config" && !name.startsWith(".") && name !== "__pycache__")
    .filter((name) => fs.existsSync(path.join(apiDir, name, "core", "authz.py")));
  if (candidates.length !== 1) {
    throw new RepoNotFound(
      `Expected exactly one Python package under ${apiDir} containing core/authz.py, ` +
        `found ${candidates.length} (${candidates.join(", ") || "none"}).`,
    );
  }
  return candidates[0]!;
}

/**
 * The tenant URL segment, read off an existing `add_router` call rather
 * than assumed: `init` rewrites "orgs" to the project's own tenant noun.
 */
function detectTenantSegment(apiDir: string): string {
  const urls = path.join(apiDir, "config", "urls.py");
  if (fs.existsSync(urls)) {
    const content = fs.readFileSync(urls, "utf8");
    const match = /ninja_api\.add_router\("\/([a-z_]+)"/.exec(content);
    if (match) return match[1]!;
  }
  return "orgs";
}

export function loadRepo(startAt?: string): Repo {
  const root = findRepoRoot(startAt);
  const apiDir = path.join(root, "apps", "api");
  const pythonPackage = detectPythonPackage(apiDir);
  return {
    root,
    apiDir,
    packageDir: path.join(apiDir, pythonPackage),
    pythonPackage,
    templatesDir: path.join(root, "templates"),
    tenantSegment: detectTenantSegment(apiDir),
  };
}

export function spliceTargets(repo: Repo) {
  return {
    settings: path.join(repo.apiDir, "config", "settings", "base.py"),
    urls: path.join(repo.apiDir, "config", "urls.py"),
    permissions: path.join(repo.packageDir, "organizations", "permissions.py"),
    roles: path.join(repo.packageDir, "organizations", "roles.py"),
    permissionTests: path.join(repo.packageDir, "organizations", "tests", "test_permissions.py"),
  };
}

export function rel(repo: Repo, absolute: string): string {
  return path.relative(repo.root, absolute).split(path.sep).join("/");
}
