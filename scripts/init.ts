#!/usr/bin/env node
/**
 * Keel template instantiation script — PRD §8 "Phase 9 — Template
 * mechanics" (renumbered Phase 17, docs/plans/phase-17.md).
 *
 * Rewrites the project name and the tenant noun across the whole repo
 * (content + file/directory names), applies the feature toggles (marketing
 * site, demo slice, billing shape, pure domain layer), regenerates the
 * lockfiles/OpenAPI/client, resets git history, and deletes the
 * template-authoring-only files (this script included) once it is done.
 *
 * Usage:
 *   node scripts/init.ts --name acme --tenant-noun team \
 *     --app-domain app.acme.com --marketing-domain acme.com --api-domain api.acme.com
 *
 * Or interactively: node scripts/init.ts
 *
 * See `node scripts/init.ts --help` for every flag, including the ones
 * (--skip-regenerate, --skip-git-reset, --skip-self-delete) that exist for
 * template CI and local iteration rather than a real instantiation.
 */

import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import * as readline from "node:readline/promises";

const REPO_ROOT = path.resolve(import.meta.dirname, "..");

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

type BillingShape = "seats" | "credits" | "both" | "neither";
type DemoSliceMode = "delete" | "keep";

interface Config {
  name: string; // slug, also the Python package / npm scope, e.g. "acme"
  tenantNoun: string; // singular, lowercase, e.g. "team"
  appDomain: string;
  marketingDomain: string;
  apiDomain: string;
  stripeSecretKey: string;
  stripePublishableKey: string;
  marketingSite: boolean;
  billing: BillingShape;
  demoSlice: DemoSliceMode;
  domainLayer: boolean;
  skipRegenerate: boolean;
  skipGitReset: boolean;
  skipSelfDelete: boolean;
  yes: boolean;
}

const FLAG_HELP = `
Keel init — instantiate this template as a new project.

Required (prompted interactively if omitted and stdin is a TTY):
  --name <slug>                 lowercase project slug, e.g. "acme"
  --tenant-noun <word>          singular lowercase tenant noun, e.g. "team"
  --app-domain <domain>         e.g. app.acme.com
  --marketing-domain <domain>   e.g. acme.com
  --api-domain <domain>         e.g. api.acme.com

Optional:
  --stripe-secret-key <key>          default: placeholder
  --stripe-publishable-key <key>     default: placeholder
  --marketing-site <yes|no>          default: yes
  --billing <seats|credits|both|neither>   default: neither
  --demo-slice <delete|keep>         default: keep
  --domain-layer <yes|no>            default: no
  --yes                              skip the confirmation prompt
  --skip-regenerate                  don't run uv lock / pnpm install / openapi / orval
  --skip-git-reset                   don't reset git history
  --skip-self-delete                 don't delete scripts/init.ts and the meta docs
  --config <file.json>               load any of the above from a JSON file
  --help                             show this message
`;

function parseArgs(argv: string[]): Partial<Config> & { configFile?: string; help?: boolean } {
  const out: Record<string, unknown> = {};
  const boolFlag = (v: string | undefined) => v === undefined || v === "yes" || v === "true";
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    switch (a) {
      case "--help":
      case "-h":
        out.help = true;
        break;
      case "--name":
        out.name = next();
        break;
      case "--tenant-noun":
        out.tenantNoun = next();
        break;
      case "--app-domain":
        out.appDomain = next();
        break;
      case "--marketing-domain":
        out.marketingDomain = next();
        break;
      case "--api-domain":
        out.apiDomain = next();
        break;
      case "--stripe-secret-key":
        out.stripeSecretKey = next();
        break;
      case "--stripe-publishable-key":
        out.stripePublishableKey = next();
        break;
      case "--marketing-site":
        out.marketingSite = boolFlag(next());
        break;
      case "--billing":
        out.billing = next();
        break;
      case "--demo-slice":
        out.demoSlice = next();
        break;
      case "--domain-layer":
        out.domainLayer = boolFlag(next());
        break;
      case "--yes":
        out.yes = true;
        break;
      case "--skip-regenerate":
        out.skipRegenerate = true;
        break;
      case "--skip-git-reset":
        out.skipGitReset = true;
        break;
      case "--skip-self-delete":
        out.skipSelfDelete = true;
        break;
      case "--config":
        out.configFile = next();
        break;
      default:
        throw new Error(`Unknown flag: ${a}`);
    }
  }
  return out as Partial<Config> & { configFile?: string; help?: boolean };
}

const DEFAULTS: Partial<Config> = {
  // Deliberately not shaped like a real Stripe key (no "sk" + "_test_" +
  // alnum-run prefix): gitleaks' stripe-access-token rule matches on that
  // shape alone regardless of what follows, so a placeholder that merely
  // *looks* like a real key still flags as a leaked secret. Fixed by
  // making the placeholder unable to pattern-match, not by allowlisting
  // a match a scanner correctly found.
  stripeSecretKey: "changeme-stripe-secret-key",
  stripePublishableKey: "changeme-stripe-publishable-key",
  marketingSite: true,
  billing: "neither",
  demoSlice: "keep",
  domainLayer: false,
  skipRegenerate: false,
  skipGitReset: false,
  skipSelfDelete: false,
  yes: false,
};

async function prompt(rl: readline.Interface, question: string, def?: string): Promise<string> {
  const suffix = def ? ` [${def}]` : "";
  const answer = (await rl.question(`${question}${suffix}: `)).trim();
  return answer || def || "";
}

async function resolveConfig(): Promise<Config> {
  const argv = process.argv.slice(2);
  const parsed = parseArgs(argv);
  if (parsed.help) {
    console.log(FLAG_HELP);
    process.exit(0);
  }

  let fileConfig: Partial<Config> = {};
  if (parsed.configFile) {
    fileConfig = JSON.parse(fs.readFileSync(parsed.configFile, "utf8"));
  }

  const merged: Partial<Config> = { ...DEFAULTS, ...fileConfig, ...parsed };
  delete (merged as Record<string, unknown>).configFile;
  delete (merged as Record<string, unknown>).help;

  const required: Array<keyof Config> = [
    "name",
    "tenantNoun",
    "appDomain",
    "marketingDomain",
    "apiDomain",
  ];
  const missing = required.filter((k) => !merged[k]);

  if (missing.length > 0) {
    if (!process.stdin.isTTY) {
      throw new Error(
        `Missing required config: ${missing.join(", ")}. Pass them as flags or --config, ` +
          `or run interactively from a terminal. See --help.`,
      );
    }
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    try {
      if (!merged.name) merged.name = await prompt(rl, "Project name (lowercase slug, e.g. acme)");
      if (!merged.tenantNoun)
        merged.tenantNoun = await prompt(rl, "Tenant noun, singular (e.g. team, tenant, practice)");
      if (!merged.appDomain) merged.appDomain = await prompt(rl, "App domain (e.g. app.acme.com)");
      if (!merged.marketingDomain)
        merged.marketingDomain = await prompt(rl, "Marketing/apex domain (e.g. acme.com)");
      if (!merged.apiDomain) merged.apiDomain = await prompt(rl, "API domain (e.g. api.acme.com)");
      merged.stripeSecretKey = await prompt(
        rl,
        "Stripe secret key (blank to fill in later)",
        merged.stripeSecretKey,
      );
      merged.stripePublishableKey = await prompt(
        rl,
        "Stripe publishable key (blank to fill in later)",
        merged.stripePublishableKey,
      );
      merged.marketingSite =
        (await prompt(
          rl,
          "Keep the marketing site? (yes/no)",
          merged.marketingSite ? "yes" : "no",
        )) !== "no";
      merged.billing = (await prompt(
        rl,
        "Billing shape (seats/credits/both/neither)",
        merged.billing,
      )) as BillingShape;
      merged.demoSlice = (await prompt(
        rl,
        "Demo slice (widgets): delete or keep as reference? (delete/keep)",
        merged.demoSlice,
      )) as DemoSliceMode;
      merged.domainLayer =
        (await prompt(
          rl,
          "Create the pure domain layer (keel/domain/)? (yes/no)",
          merged.domainLayer ? "yes" : "no",
        )) === "yes";
      if (!merged.yes) {
        const ok = await prompt(
          rl,
          "This rewrites the whole repo and resets git history. Continue? (yes/no)",
          "yes",
        );
        if (ok !== "yes") {
          console.log("Aborted.");
          process.exit(1);
        }
      }
    } finally {
      rl.close();
    }
  }

  const config = merged as Config;
  validateConfig(config);
  return config;
}

function validateConfig(c: Config): void {
  const slug = /^[a-z][a-z0-9]*$/;
  if (!slug.test(c.name)) {
    throw new Error(
      `--name must be a single lowercase alphanumeric word (got "${c.name}"). ` +
        `A hyphenated or multi-word name splits Python's snake_case and npm's kebab-case ` +
        `conventions in ways this script does not attempt to reconcile — see the report ` +
        `this script prints at the end for why.`,
    );
  }
  if (!slug.test(c.tenantNoun)) {
    throw new Error(
      `--tenant-noun must be a single lowercase alphanumeric word (got "${c.tenantNoun}").`,
    );
  }
  if (c.name === c.tenantNoun) {
    throw new Error(`--name and --tenant-noun must differ.`);
  }
  for (const [flag, value] of [
    ["--app-domain", c.appDomain],
    ["--marketing-domain", c.marketingDomain],
    ["--api-domain", c.apiDomain],
  ] as const) {
    if (!value)
      throw new Error(`${flag} is required — init refuses to complete without all three domains.`);
  }
  if (!["seats", "credits", "both", "neither"].includes(c.billing)) {
    throw new Error(`--billing must be one of seats|credits|both|neither (got "${c.billing}").`);
  }
  if (!["delete", "keep"].includes(c.demoSlice)) {
    throw new Error(`--demo-slice must be delete|keep (got "${c.demoSlice}").`);
  }
}

// ---------------------------------------------------------------------------
// Small utilities
// ---------------------------------------------------------------------------

function log(msg: string): void {
  console.log(`[init] ${msg}`);
}

function warn(msg: string): void {
  console.warn(`[init] WARNING: ${msg}`);
}

// Only pnpm needs Windows' shell mode (it resolves to a .cmd shim, which
// CreateProcess can't exec directly) — and shell mode re-tokenizes the
// whole command line, which mangles any argument containing a space or a
// punctuation character (the commit message below, an em dash included,
// is exactly such an argument). Real executables (git, uv, python) spawn
// fine as a plain argv array on every platform, so keep them off the
// shell entirely.
const NEEDS_SHELL_ON_WINDOWS = new Set(["pnpm"]);

function run(cmd: string, args: string[], cwd: string): void {
  log(`$ ${cmd} ${args.join(" ")}  (cwd: ${path.relative(REPO_ROOT, cwd) || "."})`);
  const shell = process.platform === "win32" && NEEDS_SHELL_ON_WINDOWS.has(cmd);
  execFileSync(cmd, args, { cwd, stdio: "inherit", shell });
}

function exists(p: string): boolean {
  return fs.existsSync(p);
}

function rmIfExists(p: string): void {
  if (exists(p)) {
    fs.rmSync(p, { recursive: true, force: true });
    log(`deleted ${path.relative(REPO_ROOT, p)}`);
  }
}

function readText(p: string): string {
  return fs.readFileSync(p, "utf8");
}

function writeText(p: string, content: string): void {
  fs.writeFileSync(p, content, "utf8");
}

/** Exact-substring removal used for the demo-slice's hand-written wiring
 * edits. Warns instead of throwing when the snippet has drifted, since a
 * template's reference slice is expected to change over time and a failed
 * cosmetic edit should not abort the whole run. */
function removeSnippet(file: string, snippet: string, opts: { required?: boolean } = {}): void {
  if (!exists(file)) {
    if (opts.required)
      warn(`${path.relative(REPO_ROOT, file)} not found — cannot remove a snippet from it.`);
    return;
  }
  const content = readText(file);
  if (!content.includes(snippet)) {
    warn(
      `Expected snippet not found in ${path.relative(REPO_ROOT, file)} — the reference slice ` +
        `has drifted from what this script knows. Leaving the file as-is; check it by hand.`,
    );
    return;
  }
  writeText(file, content.replace(snippet, ""));
}

function replaceSnippet(
  file: string,
  from: string,
  to: string,
  opts: { required?: boolean } = {},
): void {
  if (!exists(file)) return;
  const content = readText(file);
  if (!content.includes(from)) {
    warn(
      `Expected snippet not found in ${path.relative(REPO_ROOT, file)} — skipping a targeted edit.`,
    );
    return;
  }
  writeText(file, content.replace(from, to));
}

// ---------------------------------------------------------------------------
// Repo walking
// ---------------------------------------------------------------------------

const SKIP_DIRS = new Set([
  ".git",
  "node_modules",
  ".next",
  ".turbo",
  "dist",
  "build",
  "__pycache__",
  ".venv",
  ".pytest_cache",
  ".mypy_cache",
  ".ruff_cache",
  "coverage",
  ".content-collections",
]);

const BINARY_EXTS = new Set([
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".ico",
  ".webp",
  ".avif",
  ".woff",
  ".woff2",
  ".ttf",
  ".otf",
  ".eot",
  ".pdf",
  ".zip",
  ".gz",
  ".7z",
  ".mp4",
  ".mp3",
  ".wasm",
  ".sqlite3",
  ".pyc",
  ".so",
  ".dll",
  ".exe",
  ".bin",
]);

/** Files whose content must never go through word substitution: generated
 * artefacts that get regenerated wholesale from renamed source, or
 * lockfiles that must be regenerated by their own tool rather than
 * text-hacked (a naive rename would leave stale hashes/metadata). */
function isContentExcluded(relPath: string): boolean {
  const normalized = relPath.split(path.sep).join("/");
  return (
    normalized === "pnpm-lock.yaml" ||
    normalized === "apps/api/uv.lock" ||
    normalized === "openapi.merged.json" ||
    normalized.startsWith("packages/api-client/src/generated/")
  );
}

function walkFiles(root: string): string[] {
  const results: string[] = [];
  const stack: string[] = [root];
  while (stack.length > 0) {
    const dir = stack.pop()!;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (SKIP_DIRS.has(entry.name)) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        stack.push(full);
      } else if (entry.isFile()) {
        results.push(full);
      }
    }
  }
  return results;
}

// ---------------------------------------------------------------------------
// Case-aware word substitution engine — the tenant-noun / project-name
// rewrite. See docs/plans/phase-17.md "hard part 1": a partial rewrite
// (missing a plural, a possessive, or a compound-identifier prefix like
// `OrgScopedViewSet`) produces a project that imports fine and fails at
// runtime, so this does not rely on regex \b (which does not see a
// boundary between "Org" and "Scoped", or before "_" in "ORG_VIEW") —
// it scans literal candidate strings and decides validity from the actual
// surrounding characters.
// ---------------------------------------------------------------------------

interface CaseVariants {
  lower: string;
  title: string;
  upper: string;
}

function titleCase(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1);
}

function caseVariants(word: string): CaseVariants {
  const lower = word.toLowerCase();
  return {
    lower,
    title: lower.charAt(0).toUpperCase() + lower.slice(1),
    upper: lower.toUpperCase(),
  };
}

/** Deliberately simple: this codebase's only pluralized tenant tokens are
 * plain dictionary words / short abbreviations (organization, org), and
 * every tenant noun this prompt makes sense for (team, tenant, practice,
 * workspace, company, account) takes a plain -s. */
function pluralize(word: string): string {
  if (/[^aeiou]y$/.test(word)) return word.slice(0, -1) + "ies";
  if (/(s|x|z|ch|sh)$/.test(word)) return word + "es";
  return word + "s";
}

interface Pattern {
  literal: string;
  replacement: string;
  /** Whether an uppercase letter immediately after the match counts as a
   * valid boundary. True for ordinary dictionary words (KEEL, ORGANIZATION)
   * where there's no shorter same-cased prefix collision to worry about.
   * False for short abbreviations (ORG) that are themselves a prefix of a
   * longer all-caps word (ORGANIZATION) — there an upper-upper transition
   * must NOT count as a boundary, or "ORG" would wrongly match inside
   * "ORGANIZATION". */
  allowUpperUpperAfter: boolean;
}

function isLetter(ch: string | undefined): boolean {
  return !!ch && /[A-Za-z]/.test(ch);
}
function isUpper(ch: string): boolean {
  return /[A-Z]/.test(ch);
}
function isLower(ch: string): boolean {
  return /[a-z]/.test(ch);
}

function validBoundaryBefore(charBefore: string | undefined, matchFirstChar: string): boolean {
  if (!isLetter(charBefore)) return true; // start of string, or non-letter (incl. "_")
  // charBefore is a letter: only a lowercase->uppercase camelCase transition
  // counts as a boundary (e.g. "isOrgAdmin" -> "Org").
  return isLower(charBefore!) && isUpper(matchFirstChar);
}

function validBoundaryAfter(
  matchLastChar: string,
  charAfter: string | undefined,
  allowUpperUpperAfter: boolean,
): boolean {
  if (!isLetter(charAfter)) return true; // end of string, or non-letter (incl. "_")
  if (isLower(matchLastChar) && isUpper(charAfter!)) return true; // PascalCase boundary: "Org|Scoped"
  if (isUpper(matchLastChar) && isUpper(charAfter!)) return allowUpperUpperAfter;
  return false;
}

/** Longest-literal-first, single left-to-right pass so e.g. "organization"
 * is always preferred over "org" at the same start position — never
 * partially replacing the short form inside the long word. */
function applyPatterns(input: string, patterns: Pattern[]): string {
  if (patterns.length === 0) return input;
  const sorted = [...patterns].sort((a, b) => b.literal.length - a.literal.length);
  let out = "";
  let i = 0;
  outer: while (i < input.length) {
    for (const p of sorted) {
      const { literal } = p;
      if (input.startsWith(literal, i)) {
        const before = i === 0 ? undefined : input[i - 1];
        const after = i + literal.length >= input.length ? undefined : input[i + literal.length];
        const first = literal[0];
        const last = literal[literal.length - 1];
        if (
          validBoundaryBefore(before, first) &&
          validBoundaryAfter(last, after, p.allowUpperUpperAfter)
        ) {
          out += p.replacement;
          i += literal.length;
          continue outer;
        }
      }
    }
    out += input[i];
    i += 1;
  }
  return out;
}

/** Builds the patterns for one "long word" family (a project name, or a
 * tenant noun's US/UK spellings), singular and plural, in lower/Title/UPPER
 * case, mapped onto the equivalent case/number of the target word. */
function longWordPatterns(sourceWords: string[], target: string): Pattern[] {
  const targetSingular = caseVariants(target);
  const targetPlural = caseVariants(pluralize(target));
  const patterns: Pattern[] = [];
  for (const source of sourceWords) {
    const singular = caseVariants(source);
    const plural = caseVariants(pluralize(source));
    patterns.push(
      { literal: plural.lower, replacement: targetPlural.lower, allowUpperUpperAfter: true },
      { literal: plural.title, replacement: targetPlural.title, allowUpperUpperAfter: true },
      { literal: plural.upper, replacement: targetPlural.upper, allowUpperUpperAfter: true },
      { literal: singular.lower, replacement: targetSingular.lower, allowUpperUpperAfter: true },
      { literal: singular.title, replacement: targetSingular.title, allowUpperUpperAfter: true },
      { literal: singular.upper, replacement: targetSingular.upper, allowUpperUpperAfter: true },
    );
  }
  return patterns;
}

/** Builds the patterns for a short abbreviation family (tenant noun's "org"
 * short form). The target's short form is just the target word itself —
 * every tenant noun this prompt makes sense for (team, tenant, practice)
 * is already short. The ALL-CAPS variant disallows an upper-upper boundary
 * so it never matches as a prefix of the long word's ALL-CAPS form. */
function shortWordPatterns(sourceShort: string, target: string): Pattern[] {
  const targetSingular = caseVariants(target);
  const targetPlural = caseVariants(pluralize(target));
  const singular = caseVariants(sourceShort);
  const plural = caseVariants(pluralize(sourceShort));
  return [
    { literal: plural.lower, replacement: targetPlural.lower, allowUpperUpperAfter: true },
    { literal: plural.title, replacement: targetPlural.title, allowUpperUpperAfter: true },
    { literal: plural.upper, replacement: targetPlural.upper, allowUpperUpperAfter: false },
    { literal: singular.lower, replacement: targetSingular.lower, allowUpperUpperAfter: true },
    { literal: singular.title, replacement: targetSingular.title, allowUpperUpperAfter: true },
    { literal: singular.upper, replacement: targetSingular.upper, allowUpperUpperAfter: false },
  ];
}

/** Fixed third-party identifiers that happen to contain "org" but mean
 * something unrelated to the tenant noun — Sentry's own organization slug
 * (SENTRY_ORG env var, and the `org:` key the Sentry webpack plugin reads
 * in next.config.ts), not this project's tenant. Protected by matching the
 * exact literal and replacing it with itself, which — being longer than
 * "org"/"ORG" — wins the longest-match-first pass at that position and
 * stops the tenant-noun patterns from ever seeing it. */
function protectedLiteralPatterns(): Pattern[] {
  const literals = ["SENTRY_ORG", "org: process.env.SENTRY_ORG,"];
  return literals.map((literal) => ({ literal, replacement: literal, allowUpperUpperAfter: true }));
}

function buildAllPatterns(c: Config): Pattern[] {
  return [
    ...protectedLiteralPatterns(),
    ...longWordPatterns(["keel"], c.name),
    ...longWordPatterns(["organization", "organisation"], c.tenantNoun),
    ...shortWordPatterns("org", c.tenantNoun),
  ];
}

/** Applies the substitution to every file's content and, separately, to
 * every path segment — renames happen in a second pass, deepest paths
 * first, so a directory rename never invalidates a path still queued for
 * processing. */
function rewriteRepoWords(config: Config): void {
  const patterns = buildAllPatterns(config);
  const files = walkFiles(REPO_ROOT);
  let editedCount = 0;

  for (const file of files) {
    const relPath = path.relative(REPO_ROOT, file);
    if (isContentExcluded(relPath)) continue;
    const ext = path.extname(file).toLowerCase();
    if (BINARY_EXTS.has(ext)) continue;

    let buf: Buffer;
    try {
      buf = fs.readFileSync(file);
    } catch {
      continue;
    }
    // Skip anything that looks binary (a null byte in the first 8KB).
    if (buf.subarray(0, 8192).includes(0)) continue;

    const content = buf.toString("utf8");
    const rewritten = applyPatterns(content, patterns);
    if (rewritten !== content) {
      fs.writeFileSync(file, rewritten, "utf8");
      editedCount++;
    }
  }
  log(`rewrote content in ${editedCount} files`);

  // Rename paths. Recompute the file/dir list fresh (content edits above
  // don't change paths) and rename deepest-first.
  const allPaths: string[] = [];
  const stack: string[] = [REPO_ROOT];
  while (stack.length > 0) {
    const dir = stack.pop()!;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (SKIP_DIRS.has(entry.name)) continue;
      const full = path.join(dir, entry.name);
      allPaths.push(full);
      if (entry.isDirectory()) stack.push(full);
    }
  }
  allPaths.sort((a, b) => b.split(path.sep).length - a.split(path.sep).length);

  let renamedCount = 0;
  for (const p of allPaths) {
    if (!exists(p)) continue; // parent already renamed out from under it
    const dir = path.dirname(p);
    const base = path.basename(p);
    const newBase = applyPatterns(base, patterns);
    if (newBase !== base) {
      const target = path.join(dir, newBase);
      fs.renameSync(p, target);
      renamedCount++;
    }
  }
  log(`renamed ${renamedCount} files/directories`);
}

// ---------------------------------------------------------------------------
// Template-authoring-only docs — irrelevant, and full of stale "keel"
// references, once this stops being the template and becomes a project.
// ---------------------------------------------------------------------------

function deleteTemplateAuthoringDocs(): void {
  rmIfExists(path.join(REPO_ROOT, "docs", "plans"));
  rmIfExists(path.join(REPO_ROOT, "docs", "review-2026-08.md"));
  rmIfExists(path.join(REPO_ROOT, "docs", "marketing-removal.md"));
  rmIfExists(path.join(REPO_ROOT, "keel-prd.md"));
  rmIfExists(path.join(REPO_ROOT, ".github", "workflows", "template-ci.yml"));
}

// ---------------------------------------------------------------------------
// Marketing site removal — docs/marketing-removal.md, read and executed
// before it is deleted above by deleteTemplateAuthoringDocs(). This runs
// BEFORE the word-substitution pass, on the original "keel"/"organization"
// paths, since it is simplest to point at.
// ---------------------------------------------------------------------------

function removeMarketingSite(): void {
  const web = path.join(REPO_ROOT, "apps", "web");
  rmIfExists(path.join(web, "app", "(marketing)"));
  rmIfExists(path.join(web, "app", "sitemap.ts"));
  rmIfExists(path.join(web, "app", "robots.ts"));
  rmIfExists(path.join(web, "content"));
  rmIfExists(path.join(web, "content-collections.ts"));
  rmIfExists(path.join(web, "lib", "blog"));
  // NOT lib/site.ts / site.test.ts, despite docs/marketing-removal.md's
  // claim that they're "only used by the routes above": the root
  // app/layout.tsx (always present) reads SITE_URL for `metadataBase` —
  // deleting them breaks a page with no marketing content in it at all.
  rmIfExists(path.join(web, "components", "json-ld.tsx"));
  rmIfExists(path.join(web, "lib", "billing", "feature-labels.ts"));
  rmIfExists(path.join(web, "lib", "billing", "feature-labels.test.ts"));
  rmIfExists(path.join(web, "e2e", "marketing.spec.ts"));
  // These test the two files just deleted above, not anything that survives.
  rmIfExists(path.join(web, "app", "sitemap.test.ts"));
  rmIfExists(path.join(web, "app", "robots.test.ts"));

  // vitest.setup.ts's whole reason to exist is that app/sitemap.ts (just
  // deleted) imports the content-collections generated module — with the
  // route gone and the content-collections dependency about to be dropped
  // below, every other test would otherwise fail on this guard instead.
  replaceSnippet(
    path.join(web, "vitest.setup.ts"),
    [
      `import { existsSync } from "node:fs";`,
      `import { dirname, join } from "node:path";`,
      `import { fileURLToPath } from "node:url";`,
      ``,
      `import "@testing-library/jest-dom/vitest";`,
      ``,
      `// app/sitemap.ts imports the generated "content-collections" module, which`,
      `// the content-collections build produces into .content-collections/ (and`,
      `// which \`next dev\` produces as a side effect — the reason a missing build`,
      `// passes locally and fails in CI). The directory is generated output and is`,
      `// gitignored, so a fresh clone, a fresh worktree and CI all start without it.`,
      `//`,
      `// Left alone, the symptom is a vite resolve error pointing at sitemap.ts`,
      `// rather than at the missing build step. Fail once, up front, with the`,
      `// command to run.`,
      `const setupDir = dirname(fileURLToPath(import.meta.url));`,
      `const generated = join(setupDir, ".content-collections", "generated");`,
      ``,
      `if (!existsSync(generated)) {`,
      `  throw new Error(`,
      `    \`Content collections have not been built: \${generated} is missing.\\n\` +`,
      `      "Run \`pnpm --filter web content:build\` from the repo root first.\\n" +`,
      `      "Without it, any test touching app/sitemap.ts fails with a vite " +`,
      `      'resolve error for "content-collections" that points nowhere near the cause.',`,
      `  );`,
      `}`,
    ].join("\n"),
    `import "@testing-library/jest-dom/vitest";`,
    { required: true },
  );

  // apps/web/package.json: drop the content-collections deps and script.
  const pkgPath = path.join(web, "package.json");
  const pkg = JSON.parse(readText(pkgPath));
  for (const dep of [
    "@content-collections/cli",
    "@content-collections/core",
    "@content-collections/mdx",
    "@content-collections/next",
  ]) {
    delete pkg.dependencies?.[dep];
    delete pkg.devDependencies?.[dep];
  }
  if (pkg.scripts?.typecheck) {
    pkg.scripts.typecheck = pkg.scripts.typecheck.replace(/pnpm run content:build\s*&&\s*/, "");
  }
  delete pkg.scripts?.["content:build"];
  writeText(pkgPath, JSON.stringify(pkg, null, 2) + "\n");

  // next.config.ts: drop the withContentCollections(...) wrapper. It sits
  // between nextConfig and withSentryConfig (two of headers/
  // skipTrailingSlashRedirect get re-applied after it because it drops
  // them) — remove the import and collapse the wrapper to a passthrough
  // rather than trying to unwrap the call generically.
  const nextConfigPath = path.join(web, "next.config.ts");
  removeSnippet(
    nextConfigPath,
    `import { withContentCollections } from "@content-collections/next";\n`,
  );
  removeSnippet(
    nextConfigPath,
    [
      `// Wires apps/web/content-collections.ts into the Next.js build (phase-7.md`,
      `// 7.4). Removing the marketing route group (PRD §8 Phase 9) means dropping`,
      `// this wrapper too — see docs/marketing-removal.md.`,
      `//`,
      `// withContentCollections returns a config object with several of`,
      `// nextConfig's own keys silently absent rather than merged through —`,
      `// verified directly: \`headers\` and \`skipTrailingSlashRedirect\` are both`,
      `// \`undefined\` on its return value even when present on the object passed`,
      `// in. Whatever it does internally, it isn't a full-config passthrough, so`,
      `// those two are re-applied explicitly afterward rather than trusted to`,
      `// have survived.`,
      ``,
    ].join("\n"),
  );
  replaceSnippet(
    nextConfigPath,
    [
      `const configWithContentCollections: NextConfig = {`,
      `  ...withContentCollections(nextConfig),`,
      `  headers: nextConfig.headers,`,
      `  skipTrailingSlashRedirect: nextConfig.skipTrailingSlashRedirect,`,
      `};`,
    ].join("\n"),
    `const configWithContentCollections: NextConfig = nextConfig;`,
  );

  // tsconfig.json / vitest.config.ts: drop the content-collections alias.
  const tsconfigPath = path.join(web, "tsconfig.json");
  if (exists(tsconfigPath)) {
    const tsconfig = JSON.parse(readText(tsconfigPath));
    if (tsconfig.compilerOptions?.paths) {
      delete tsconfig.compilerOptions.paths["content-collections"];
    }
    writeText(tsconfigPath, JSON.stringify(tsconfig, null, 2) + "\n");
  }
  const vitestConfigPath = path.join(web, "vitest.config.ts");
  removeSnippet(
    vitestConfigPath,
    [
      `      // Mirrors tsconfig.json's "content-collections" path alias to the`,
      `      // generated output of content-collections.ts (apps/web/lib/blog).`,
      `      "content-collections": path.resolve(__dirname, ".content-collections/generated"),`,
      ``,
    ].join("\n"),
  );

  // NEXT_PUBLIC_SITE_URL stays in .env.example — lib/site.ts stays too,
  // see the comment above its non-deletion.
}

// ---------------------------------------------------------------------------
// Demo slice (widgets) — delete, or move to docs/reference-slice/ as inert
// reference code. Either way the live wiring (INSTALLED_APPS, the Ninja
// router, the frontend nav/command-palette integration) is removed; the
// generated OpenAPI/TS client naturally drops the widgets endpoints on the
// next regeneration once the router is gone, so there is nothing to hand-
// edit in packages/api-client.
// ---------------------------------------------------------------------------

function handleDemoSlice(config: Config): void {
  const apiDir = path.join(REPO_ROOT, "apps", "api", config.name);
  const webDir = path.join(REPO_ROOT, "apps", "web");
  const widgetsApiDir = path.join(apiDir, "widgets");
  const widgetsWebPagesDir = path.join(
    webDir,
    "app",
    "(app)",
    "app",
    `[${config.tenantNoun}]`,
    "widgets",
  );
  const widgetsWebLibDir = path.join(webDir, "lib", "widgets");

  // --- Backend wiring -------------------------------------------------
  const settingsPath = path.join(REPO_ROOT, "apps", "api", "config", "settings", "base.py");
  removeSnippet(settingsPath, `    "${config.name}.widgets",\n`);

  const urlsPath = path.join(REPO_ROOT, "apps", "api", "config", "urls.py");
  removeSnippet(urlsPath, `from ${config.name}.widgets.views import router as widgets_router\n`);
  removeSnippet(
    urlsPath,
    `ninja_api.add_router("/${pluralize(config.tenantNoun)}", widgets_router)\n`,
  );

  const pyprojectPath = path.join(REPO_ROOT, "apps", "api", "pyproject.toml");
  removeSnippet(pyprojectPath, `    "${config.name}.widgets",\n`);

  // --- Frontend wiring (apps/web/app/(app)/layout.tsx) -----------------
  const appLayoutPath = path.join(webDir, "app", "(app)", "layout.tsx");
  const Tenant = titleCase(config.tenantNoun);
  removeSnippet(appLayoutPath, `import { listWidgets } from "@/lib/widgets/api";\n`);
  removeSnippet(
    appLayoutPath,
    `  const [widgetResults, setWidgetResults] = useState<{ id: string; name: string }[]>([]);\n`,
  );
  removeSnippet(
    appLayoutPath,
    `      { href: \`/\${params.${config.tenantNoun}}/widgets\`, label: "Widgets", requires: Perm.WIDGETS_VIEW },\n`,
  );
  removeSnippet(
    appLayoutPath,
    [
      `  // Resource search: filters by name against the current page of`,
      `  // widgets. A real project's palette would back this with a proper`,
      `  // search endpoint; this demo resource has no such index, so it's a`,
      `  // client-side substring match over what's already paginated in.`,
      `  useEffect(() => {`,
      `    if (!paletteOpen || !current${Tenant}?.permissions.includes(Perm.WIDGETS_VIEW) || !paletteQuery) {`,
      `      setWidgetResults([]);`,
      `      return;`,
      `    }`,
      `    let cancelled = false;`,
      `    listWidgets(current${Tenant}.slug)`,
      `      .then((page) => {`,
      `        if (cancelled) return;`,
      `        const query = paletteQuery.toLowerCase();`,
      `        setWidgetResults(page.results.filter((w) => w.name.toLowerCase().includes(query)));`,
      `      })`,
      `      .catch(() => {`,
      `        if (!cancelled) setWidgetResults([]);`,
      `      });`,
      `    return () => {`,
      `      cancelled = true;`,
      `    };`,
      `  }, [paletteOpen, paletteQuery, current${Tenant}]);`,
      ``,
      ``,
    ].join("\n"),
  );
  removeSnippet(
    appLayoutPath,
    [
      `    // Nav visibility is presentation only, the same as <Can> (components`,
      `    // /${config.tenantNoun}/can.tsx) — the widgets route itself still enforces`,
      `    // Perm.WIDGETS_VIEW server-side regardless of whether a link to it`,
      `    // is rendered here.`,
      ``,
    ].join("\n"),
  );
  removeSnippet(
    appLayoutPath,
    [
      `    const widgetCommands: CommandItem[] = widgetResults.map((widget) => ({`,
      `      id: \`widget-\${widget.id}\`,`,
      `      label: widget.name,`,
      `      group: "Widgets",`,
      `      onSelect: () => router.push(\`/\${params.${config.tenantNoun}}/widgets/\${widget.id}\`),`,
      `    }));`,
      ``,
    ].join("\n"),
  );
  replaceSnippet(
    appLayoutPath,
    `const all = [...navCommands, ...${config.tenantNoun}Commands, ...widgetCommands];`,
    `const all = [...navCommands, ...${config.tenantNoun}Commands];`,
  );
  replaceSnippet(
    appLayoutPath,
    [
      `    return all.filter(`,
      `      (item) => item.group === "Widgets" || item.label.toLowerCase().includes(query),`,
      `    );`,
    ].join("\n"),
    `    return all.filter((item) => item.label.toLowerCase().includes(query));`,
  );
  replaceSnippet(
    appLayoutPath,
    `}, [navItems, me, paletteQuery, router, widgetResults, params.${config.tenantNoun}]);`,
    `}, [navItems, me, paletteQuery, router, params.${config.tenantNoun}]);`,
  );
  // Perm.WIDGETS_VIEW was the only use of this import in the layout.
  removeSnippet(appLayoutPath, `import { Perm } from "@/lib/${config.tenantNoun}/permissions";\n`);

  const dashboardPagePath = path.join(
    webDir,
    "app",
    "(app)",
    "app",
    `[${config.tenantNoun}]`,
    "page.tsx",
  );
  if (exists(dashboardPagePath)) {
    let content = readText(dashboardPagePath);
    content = content.replace(
      /\s*<Link\s+href=\{`\/\$\{current[A-Za-z]+\.slug\}\/widgets`\}[\s\S]*?<\/Link>\n/,
      "\n",
    );
    // That was the dashboard page's only use of <Link>.
    if (!content.includes("<Link")) {
      content = content.replace(/import Link from "next\/link";\n/, "");
    }
    writeText(dashboardPagePath, content);
  }

  const permissionsPath = path.join(webDir, "lib", config.tenantNoun, "permissions.ts");
  removeSnippet(permissionsPath, `  WIDGETS_VIEW: "widgets.view",\n`);
  removeSnippet(permissionsPath, `  WIDGETS_MANAGE: "widgets.manage",\n`);

  const a11ySpecPath = path.join(webDir, "e2e", "app-accessibility.spec.ts");
  removeSnippet(a11ySpecPath, `      \`/\${${config.tenantNoun}.slug}/widgets\`,\n`);

  // audit/tests/test_recorder.py's impersonator test used the demo
  // resource's own service as a stand-in "some audited service" — the one
  // real cross-app import onto the demo slice that isn't a comment or a
  // string literal (mypy catches it; grep for "widget" doesn't, since it
  // doesn't distinguish an import from a docstring mention). Replaced with
  // a self-contained audited function defined in the test itself, which
  // is arguably the better test anyway: it stops a core infrastructure
  // test depending on the one app `init` might have just deleted.
  const recorderTestPath = path.join(
    REPO_ROOT,
    "apps",
    "api",
    config.name,
    "audit",
    "tests",
    "test_recorder.py",
  );
  replaceSnippet(
    recorderTestPath,
    [
      `def test_audited_service_records_the_impersonator(django_capture_on_commit_callbacks) -> None:`,
      `    """Proves the recorder's impersonator handling (docs/plans/phase-8.md`,
      `    8.1) against a service the PRD §6 restrictions don't cover — widget`,
      `    CRUD isn't one of the four restricted actions, so an impersonated`,
      `    session performing it is exactly the case PRD §6 says must still be`,
      `    recorded ("every subsequent AuditLog row carries impersonator")."""`,
      `    from ${config.name}.widgets import services as widget_services`,
      `    from ${config.name}.widgets.models import Widget`,
      ``,
      `    ${config.tenantNoun} = _${config.tenantNoun}()`,
      `    actor = User.objects.create_user(email="actor3@example.com", password="s3cret-pass")`,
      `    staff = User.objects.create_user(`,
      `        email="staff@example.com", password="s3cret-pass", is_staff=True`,
      `    )`,
      `    widget = Widget.objects.create(`,
      `        ${config.tenantNoun}=${config.tenantNoun}, name="Old name", description="", status="active", created_by=actor`,
      `    )`,
      ``,
      `    with django_capture_on_commit_callbacks(execute=True):`,
      `        widget_services.update_widget(`,
      `            widget=widget, actor=actor, impersonator=staff, name="New name"`,
      `        )`,
      ``,
      `    row = AuditLog.objects.get(action="widget.updated", target_id=str(widget.pk))`,
      `    assert row.actor_id == actor.pk`,
      `    assert row.impersonator_id == staff.pk`,
    ].join("\n"),
    [
      `def test_audited_service_records_the_impersonator(django_capture_on_commit_callbacks) -> None:`,
      `    """Proves the recorder's impersonator handling (docs/plans/phase-8.md`,
      `    8.1) generically: any @audited function has its impersonator kwarg`,
      `    picked up by the wrapper (${config.name}/core/audit.py), independent of`,
      `    whether the wrapped function's own signature does anything with it."""`,
      `    from ${config.name}.core.audit import audited`,
      ``,
      `    @audited("test.impersonated_action")`,
      `    def _do_something(*, actor: User, impersonator: User | None = None) -> None:`,
      `        return None`,
      ``,
      `    actor = User.objects.create_user(email="actor3@example.com", password="s3cret-pass")`,
      `    staff = User.objects.create_user(`,
      `        email="staff@example.com", password="s3cret-pass", is_staff=True`,
      `    )`,
      ``,
      `    with django_capture_on_commit_callbacks(execute=True):`,
      `        _do_something(actor=actor, impersonator=staff)`,
      ``,
      `    row = AuditLog.objects.get(action="test.impersonated_action")`,
      `    assert row.actor_id == actor.pk`,
      `    assert row.impersonator_id == staff.pk`,
    ].join("\n"),
    { required: true },
  );

  // --- The reference-slice code itself ---------------------------------
  if (config.demoSlice === "delete") {
    rmIfExists(widgetsApiDir);
    rmIfExists(widgetsWebPagesDir);
    rmIfExists(widgetsWebLibDir);
  } else {
    const refDir = path.join(REPO_ROOT, "docs", "reference-slice");
    fs.mkdirSync(refDir, { recursive: true });
    if (exists(widgetsApiDir)) fs.renameSync(widgetsApiDir, path.join(refDir, "api-widgets"));
    if (exists(widgetsWebPagesDir))
      fs.renameSync(widgetsWebPagesDir, path.join(refDir, "web-widgets-pages"));
    if (exists(widgetsWebLibDir))
      fs.renameSync(widgetsWebLibDir, path.join(refDir, "web-widgets-lib"));
    writeText(
      path.join(refDir, "README.md"),
      [
        "# Reference slice: widgets",
        "",
        "Inert copy of the demo CRUD vertical slice — not an installed app, not",
        "on any router, not built, not covered by the coverage gate. It is here",
        "so `/new-resource` and `/new-readonly-resource` (and anyone typing",
        `\`make this look like the reference slice\`) have a real, complete example`,
        "to copy the shape of, rather than a prose description of one.",
        "",
        "- `api-widgets/` — the Django app: models, services, selectors,",
        "  serializers, views, tests.",
        "- `web-widgets-pages/` — the Next.js list/detail/create pages.",
        "- `web-widgets-lib/` — the typed API client wrapper the pages call.",
        "",
        "Run `init` again with `--demo-slice delete` to remove this directory,",
        "or delete it by hand — nothing else in the repo imports from here.",
        "",
      ].join("\n"),
    );
  }
}

// ---------------------------------------------------------------------------
// Pure domain layer
// ---------------------------------------------------------------------------

function handleDomainLayer(config: Config): void {
  if (!config.domainLayer) return;
  const domainDir = path.join(REPO_ROOT, "apps", "api", config.name, "domain");
  fs.mkdirSync(domainDir, { recursive: true });
  // tests/test_domain_contract.py requires this file's AST body to be
  // empty (a module docstring is an ast.Expr statement, not "no code") —
  // plain "#" comments, never a docstring, or that meta-test fails.
  writeText(
    path.join(domainDir, "__init__.py"),
    [
      "# Pure domain layer (PRD §4 invariant 1).",
      "#",
      "# Code in this package may never import Django, Celery, or any other",
      `# ${config.name}.* package — enforced by the "${config.name}.domain is independent"`,
      "# import-linter contract in apps/api/pyproject.toml, which is a no-op",
      "# until this directory has a file in it.",
      "#",
      "# Put logic here only once a rule genuinely has no framework dependency",
      "# left in it: pricing math, a state machine, a scoring function. Most",
      "# business logic belongs in services.py/selectors.py instead — see",
      "# CLAUDE.md.",
      "#",
      "# This file itself must stay empty of actual code — see",
      "# tests/test_domain_contract.py for why — put rules in a submodule,",
      "# e.g. domain/pricing.py.",
      "",
    ].join("\n"),
  );
  log(`created ${path.relative(REPO_ROOT, domainDir)}/ and activated its import-linter contract`);
}

// ---------------------------------------------------------------------------
// Billing shape
// ---------------------------------------------------------------------------

function handleBillingShape(config: Config): void {
  const seats = config.billing === "seats" || config.billing === "both";
  const credits = config.billing === "credits" || config.billing === "both";
  const envExamplePath = path.join(REPO_ROOT, ".env.example");
  if (!exists(envExamplePath)) return;
  let content = readText(envExamplePath);
  content = content.replace(/^BILLING_CREDITS=.*$/m, `BILLING_CREDITS=${credits}`);
  content = content.replace(/^BILLING_SEAT_PRICING=.*$/m, `BILLING_SEAT_PRICING=${seats}`);
  content = content.replace(
    /^NEXT_PUBLIC_BILLING_CREDITS=.*$/m,
    `NEXT_PUBLIC_BILLING_CREDITS=${credits}`,
  );
  writeText(envExamplePath, content);
  log(`billing shape: seats=${seats} credits=${credits}`);
}

// ---------------------------------------------------------------------------
// Domains, Stripe keys, and .env
// ---------------------------------------------------------------------------

function applyDomainsAndSecrets(config: Config): void {
  // Every doc/comment in the template uses acme.com/app.acme.com/api.acme.com
  // as the worked example. Swap the placeholder for the real domains
  // wherever it appears, repo-wide, in the same pass as everything else
  // would if it ran later — done here, once, directly.
  const patterns: Pattern[] = [
    { literal: "app.acme.com", replacement: config.appDomain, allowUpperUpperAfter: true },
    { literal: "api.acme.com", replacement: config.apiDomain, allowUpperUpperAfter: true },
    { literal: "acme.com", replacement: config.marketingDomain, allowUpperUpperAfter: true },
  ];
  const files = walkFiles(REPO_ROOT);
  for (const file of files) {
    const relPath = path.relative(REPO_ROOT, file);
    if (isContentExcluded(relPath)) continue;
    const ext = path.extname(file).toLowerCase();
    if (BINARY_EXTS.has(ext)) continue;
    let buf: Buffer;
    try {
      buf = fs.readFileSync(file);
    } catch {
      continue;
    }
    if (buf.subarray(0, 8192).includes(0)) continue;
    const content = buf.toString("utf8");
    const rewritten = applyPatterns(content, patterns);
    if (rewritten !== content) fs.writeFileSync(file, rewritten, "utf8");
  }

  // Write a real .env from .env.example, filling in the Stripe keys. Dev
  // still runs on the lvh.me scheme (DJANGO_ALLOWED_HOSTS etc.) — that
  // trick is independent of the project's real domains, which matter at
  // deploy time (docs/deploy-railway.md) rather than in dev.
  const envExamplePath = path.join(REPO_ROOT, ".env.example");
  const envPath = path.join(REPO_ROOT, ".env");
  if (exists(envExamplePath) && !exists(envPath)) {
    let content = readText(envExamplePath);
    if (!/^STRIPE_SECRET_KEY=/m.test(content)) {
      content +=
        `\n# --- Stripe (apps/api/${config.name}/billing) ------------------------------------------\n` +
        `STRIPE_SECRET_KEY=${config.stripeSecretKey}\n` +
        `STRIPE_WEBHOOK_SECRET=\n` +
        `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=${config.stripePublishableKey}\n`;
    } else {
      content = content.replace(
        /^STRIPE_SECRET_KEY=.*$/m,
        `STRIPE_SECRET_KEY=${config.stripeSecretKey}`,
      );
      content = content.replace(
        /^NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=.*$/m,
        `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=${config.stripePublishableKey}`,
      );
    }
    writeText(envPath, content);
    log("wrote .env from .env.example with the Stripe keys filled in");
    log(
      "Stripe plan sync was not run — it needs a live Stripe account. Once real keys are in " +
        "place, run: uv run python manage.py sync_stripe_plans (apps/api).",
    );
  }
}

// ---------------------------------------------------------------------------
// CLAUDE.md / docs cleanup and docs/brand-pass.md
// ---------------------------------------------------------------------------

function regenerateDocs(config: Config): void {
  const claudeMdPath = path.join(REPO_ROOT, "CLAUDE.md");
  if (exists(claudeMdPath)) {
    let content = readText(claudeMdPath);
    // The Ninja migration this note warned about is done — every pattern
    // in the file already reflects it. Leaving the note in would tell an
    // agent working on a fresh project to go read an ADR about a migration
    // that finished before the project existed.
    content = content.replace(/- \*\*ADR 0001 replaces DRF with Ninja[^\n]*\n(?:  [^\n]*\n)*/, "");
    content = content.replace(/- No migrations outside a phase that declares one[^\n]*\n/, "");
    // keel-prd.md was the template-authoring spec — deleted by
    // deleteTemplateAuthoringDocs(), so this project's CLAUDE.md can't
    // point an agent at it any more.
    content = content.replace(new RegExp(` and \`${config.name}-prd\\.md\` §4;`), ";");
    if (config.demoSlice === "delete") {
      content = content.replace(
        new RegExp(
          `\`apps/api/${config.name}/widgets/\` is the reference slice — copy its shape, not its\\ncontent\\.\\n`,
        ),
        `There is no reference slice in this project — the demo resource was\nremoved at instantiation (\`init --demo-slice delete\`).\n`,
      );
    } else {
      content = content.replace(
        new RegExp(
          `\`apps/api/${config.name}/widgets/\` is the reference slice — copy its shape, not its\\ncontent\\.`,
        ),
        "The demo resource was moved to `docs/reference-slice/` at instantiation " +
          "— copy its shape, not its content.",
      );
    }
    writeText(claudeMdPath, content);
  }

  // README.md's opening still describes the template repo, not the
  // project this instantiation produced: it points at keel-prd.md,
  // docs/review-2026-08.md and docs/plans/ (all deleted above) and
  // says instantiation doesn't exist yet.
  const readmePath = path.join(REPO_ROOT, "README.md");
  if (exists(readmePath)) {
    let content = readText(readmePath);
    content = content.replace(
      new RegExp(
        `\`${config.name}-prd\\.md\` is the specification and the reasoning behind it\\. This file is how to run the thing\\.`,
      ),
      "This file is how to run the thing.",
    );
    content = content.replace(
      /\*\*Status:\*\* [^\n]*\n/,
      `**Status:** instantiated from the Keel template (tenant noun: "${config.tenantNoun}").\n`,
    );
    content = content.replace(
      new RegExp(`\`docs/review-2026-08\\.md\` is the current state of the repository[^\\n]*\\n`),
      "",
    );
    writeText(readmePath, content);
  }

  writeText(
    path.join(REPO_ROOT, "docs", "brand-pass.md"),
    [
      `# Brand pass — first task after instantiation`,
      "",
      `\`init\` renamed the project to **${config.name}** and the tenant noun to`,
      `**${config.tenantNoun}**. It did not, and cannot, do the following —`,
      "treat this as the first checklist for the project, not an afterthought:",
      "",
      "- [ ] Replace the placeholder logo/favicon under `apps/web/public/`.",
      "- [ ] Pick real fonts and a color palette in `packages/ui/theme.css`",
      "      (still the generic template defaults).",
      "- [ ] Write real marketing copy for the pages under `apps/web/app/(marketing)/`" +
        (config.marketingSite ? "" : " — skip, the marketing site was declined."),
      "- [ ] Fill in `STRIPE_WEBHOOK_SECRET` in `.env` once a webhook endpoint",
      "      exists in the Stripe dashboard for this project.",
      "- [ ] Point DNS at the three domains chosen during `init`:",
      `      \`${config.appDomain}\`, \`${config.marketingDomain}\`, \`${config.apiDomain}\`.`,
      "- [ ] Run `uv run python manage.py sync_stripe_plans` once real Stripe",
      "      keys and products exist.",
      "- [ ] Read `docs/deploy-railway.md` (or the self-host compose file) before",
      "      the first real deploy — both guides assume this checklist is done.",
      "",
    ].join("\n"),
  );
}

// ---------------------------------------------------------------------------
// Regeneration: lockfiles, OpenAPI, generated TS client
// ---------------------------------------------------------------------------

function regenerate(config: Config): void {
  if (config.skipRegenerate) {
    warn(
      "--skip-regenerate set — lockfiles/OpenAPI/client are stale until you regenerate them by hand.",
    );
    return;
  }
  const apiDir = path.join(REPO_ROOT, "apps", "api");
  // A relative path here, not an absolute one: an absolute REPO_ROOT can
  // contain spaces, and execFileSync's Windows shell mode does not
  // reliably re-quote an argument that already contains them.
  const mergeOpenapiRel = path.relative(
    apiDir,
    path.join(REPO_ROOT, "scripts", "merge_openapi.py"),
  );
  run("uv", ["lock"], apiDir);
  run("uv", ["sync", "--all-extras"], apiDir);

  // Renaming a model/field (Organization -> Team, organization_id -> team_id)
  // is a schema change Django's own migration state doesn't know about yet
  // — `makemigrations --check` would demand a "rename" migration full of
  // the tenant noun's old name. Invariant 4 is "one baseline migration per
  // app": a fresh project has no real deployed database yet, so start that
  // baseline over instead of carrying a rename step nothing ever ran
  // against.
  const pkgDir = path.join(apiDir, config.name);
  for (const app of fs.readdirSync(pkgDir, { withFileTypes: true })) {
    if (!app.isDirectory()) continue;
    const migrationsDir = path.join(pkgDir, app.name, "migrations");
    if (!exists(migrationsDir)) continue;
    for (const file of fs.readdirSync(migrationsDir)) {
      if (/^\d{4}_.*\.py$/.test(file)) fs.rmSync(path.join(migrationsDir, file));
    }
  }
  run("uv", ["run", "python", "manage.py", "makemigrations"], apiDir);

  // Renaming shifts import alphabetization (e.g. "Organization" sorted
  // before "Role"; "Team" sorts after it) and occasionally a line past the
  // 100-column limit by however many characters the tenant noun grew.
  // Format *first*: it rewraps those overlong lines, so `check` sees them
  // as already fixed rather than reporting an E501 `--fix` can't touch
  // (line-wrapping isn't one of ruff check's autofixes) — reversing this
  // order once left real, un-reported lint errors sitting in a project
  // `init` had just claimed was clean.
  run("uv", ["run", "ruff", "format", "."], apiDir);
  try {
    run("uv", ["run", "ruff", "check", "--fix", "."], apiDir);
  } catch {
    // --fix's own remaining-issues exit is expected mid-pipeline — the
    // reformat below plus the unguarded check after it is the real gate.
  }
  // --fix's import reordering can itself leave a line for format to
  // rewrap again.
  run("uv", ["run", "ruff", "format", "."], apiDir);
  // Deliberately not wrapped in try/catch: a project must not come out of
  // `init` with lint errors already baked in. Anything still failing here
  // fails the whole run instead of a silent warning nobody reads.
  run("uv", ["run", "ruff", "check", "."], apiDir);
  run("uv", ["run", "python", mergeOpenapiRel], apiDir);
  // CI runs with CI=true, under which pnpm defaults to --frozen-lockfile —
  // and package renames (e.g. @keel/tsconfig -> @acme/tsconfig) are
  // exactly the importer-name change frozen-lockfile mode exists to
  // reject. This install is legitimately rewriting the lockfile to match
  // the renamed packages, not drifting from a lockfile that should have
  // been committed alongside a source change.
  run("pnpm", ["install", "--no-frozen-lockfile"], REPO_ROOT);
  run("pnpm", ["--filter", `@${config.name}/api-client`, "generate"], REPO_ROOT);
  // apps/api's conftest.py refuses to collect tests until this exists
  // (docs/pre-push.md, docs/plans/phase-8.md 8.4's "build artefact the
  // test suite silently depends on" finding) — not committed, so a fresh
  // instantiation needs it built once, same as any other fresh clone.
  run("pnpm", ["--filter", `@${config.name}/emails`, "build"], REPO_ROOT);
  try {
    run("pnpm", ["exec", "prettier", "--write", "."], REPO_ROOT);
  } catch {
    warn("prettier --write reported issues — see its output above.");
  }
}

// ---------------------------------------------------------------------------
// Git history reset
// ---------------------------------------------------------------------------

function resetGitHistory(config: Config): void {
  if (config.skipGitReset) {
    warn("--skip-git-reset set — git history was left as-is.");
    return;
  }
  const gitDir = path.join(REPO_ROOT, ".git");
  rmIfExists(gitDir);
  run("git", ["init"], REPO_ROOT);
  run("git", ["add", "-A"], REPO_ROOT);
  run(
    "git",
    ["commit", "-m", `Initial commit — ${config.name}, instantiated from the Keel template`],
    REPO_ROOT,
  );
  log("git history reset to a single initial commit");
}

// ---------------------------------------------------------------------------
// Self cleanup
// ---------------------------------------------------------------------------

function selfDelete(config: Config): void {
  if (config.skipSelfDelete) {
    warn("--skip-self-delete set — scripts/init.ts and its docs were left in place.");
    return;
  }
  // Best-effort: deleting our own source file while running is safe on
  // every platform Node supports here (the module is already fully read
  // and compiled), but this still shouldn't be fatal if it fails.
  try {
    rmIfExists(path.join(REPO_ROOT, "scripts", "init.ts"));
  } catch (e) {
    warn(`could not delete scripts/init.ts: ${(e as Error).message}`);
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const config = await resolveConfig();

  log(`instantiating as "${config.name}" (tenant noun: "${config.tenantNoun}")`);

  deleteTemplateAuthoringDocs();
  if (!config.marketingSite) removeMarketingSite();
  rewriteRepoWords(config);
  handleDemoSlice(config);
  handleDomainLayer(config);
  handleBillingShape(config);
  applyDomainsAndSecrets(config);
  regenerateDocs(config);
  regenerate(config);
  resetGitHistory(config);
  selfDelete(config);

  log("done.");
  log(
    "Next: read docs/brand-pass.md, then apps/api `uv run python manage.py migrate` and `pnpm dev`.",
  );
}

main().catch((err) => {
  console.error(`[init] FAILED: ${err instanceof Error ? err.message : err}`);
  process.exit(1);
});
