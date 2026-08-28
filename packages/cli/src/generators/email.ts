/**
 * `gen email <Name>` (docs/plans/phase-19.md 19.C) — ports
 * `.claude/commands/new-email.md`'s mechanical half: the react-email
 * template (props, `{{TOKEN}}` defaults, and — when one token is a URL —
 * the button and its plain-text fallback link) and the Python sender in
 * `keel/notifications/emails.py`, calling the one `_send` helper every
 * other sender uses. The body copy, and wiring a call site to dispatch
 * the email via a Tier-1 task, are judgement and stay the slash command's
 * job (new-email.md steps 3-4) — see the TODO the template leaves.
 */

import * as fs from "node:fs";
import * as path from "node:path";

import { formatTs } from "../format-ts.js";
import { formatPython } from "../format.js";
import type { Names } from "../naming.js";
import { namesFor } from "../naming.js";
import { Plan, reportPlan } from "../plan.js";
import type { Repo } from "../repo.js";
import { loadRepo, rel } from "../repo.js";
import { render, renderPath } from "../template.js";

export class EmailGeneratorError extends Error {}

const TOKEN_RE = /^[A-Z][A-Z0-9_]*$/;

export interface EmailOptions {
  name: string;
  subject?: string;
  tokens?: string;
  dryRun: boolean;
  force: boolean;
}

function parseTokens(spec: string | undefined): string[] {
  const raw = spec?.trim() ? spec.split(",").map((t) => t.trim()) : ["ACTION_URL"];
  for (const token of raw) {
    if (!TOKEN_RE.test(token)) {
      throw new EmailGeneratorError(
        `--tokens entry "${token}" must be UPPER_SNAKE — it becomes a {{TOKEN}} placeholder ` +
          `and a Python dict key, e.g. "ACCEPT_URL".`,
      );
    }
  }
  if (new Set(raw).size !== raw.length) {
    throw new EmailGeneratorError(`--tokens has a duplicate entry: ${spec}`);
  }
  return raw;
}

/** `ACCEPT_URL` -> `acceptUrl` (template prop) / `accept_url` (Python param). */
function camelFromUpperSnake(token: string): string {
  const parts = token.toLowerCase().split("_");
  return parts
    .map((part, i) => (i === 0 ? part : part.charAt(0).toUpperCase() + part.slice(1)))
    .join("");
}

function snakeFromUpperSnake(token: string): string {
  return token.toLowerCase();
}

function kebabName(names: Names): string {
  return names.resource.replace(/_/g, "-");
}

function escapeDouble(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function buildInserts(names: Names, subject: string, tokens: string[]): Record<string, string[]> {
  const primaryUrlToken = tokens.find((t) => t.endsWith("_URL"));
  const escapedSubject = escapeDouble(subject);

  const cta_block = primaryUrlToken
    ? [
        "      <Button",
        `        href={${camelFromUpperSnake(primaryUrlToken)}}`,
        '        style={{ background: "#18181b", color: "#fff", padding: "12px 20px", borderRadius: "6px" }}',
        "      >",
        "        TODO",
        "      </Button>",
        `      <Text>Or paste this link into your browser: {${camelFromUpperSnake(primaryUrlToken)}}</Text>`,
      ]
    : [];

  return {
    token_props: tokens.map((t) => `  ${camelFromUpperSnake(t)}?: string;`),
    token_defaults: tokens.map(
      (t) => `  const ${camelFromUpperSnake(t)} = props.${camelFromUpperSnake(t)} ?? "{{${t}}}";`,
    ),
    preview_prop: [`      preview="${escapedSubject}"`],
    heading_prop: [`      heading="${escapedSubject}"`],
    cta_block,
  };
}

function senderLines(names: Names, subject: string, tokens: string[]): string[] {
  const kebab = kebabName(names);
  const params = tokens.map((t) => `${snakeFromUpperSnake(t)}: str`).join(", ");
  const dict = tokens.map((t) => `"${t}": ${snakeFromUpperSnake(t)}`).join(", ");
  return [
    "",
    "",
    `def send_${names.resource}_email(*, to: str, ${params}) -> None:`,
    "    _send(",
    "        to=to,",
    `        subject="${escapeDouble(subject)}",`,
    `        template_name="${kebab}",`,
    `        tokens={${dict}},`,
    "    )",
  ];
}

export function generateEmail(options: EmailOptions): number {
  const repo = loadRepo();
  const names = namesFor(options.name);
  if (!options.subject?.trim()) {
    throw new EmailGeneratorError(
      '`gen email` needs --subject, e.g. --subject "Your trial is ending soon".',
    );
  }
  const tokens = parseTokens(options.tokens);
  const kebab = kebabName(names);

  const emailsPackageDir = path.join(repo.root, "packages", "emails");
  const templatePath = path.join(repo.templatesDir, "email", "template.tsx");
  if (!fs.existsSync(templatePath)) {
    throw new EmailGeneratorError(`Template not found at ${rel(repo, templatePath)}.`);
  }
  const destTemplate = path.join(emailsPackageDir, "templates", `${kebab}.tsx`);
  if (fs.existsSync(destTemplate) && !options.force) {
    throw new EmailGeneratorError(
      `${rel(repo, destTemplate)} already exists. Pass --force to overwrite it. Nothing was written.`,
    );
  }

  const emailsPyPath = path.join(repo.packageDir, "notifications", "emails.py");
  if (!fs.existsSync(emailsPyPath)) {
    throw new EmailGeneratorError(`${rel(repo, emailsPyPath)} does not exist.`);
  }
  const emailsPySource = fs.readFileSync(emailsPyPath, "utf8");
  const senderMarker = `def send_${names.resource}_email(`;
  const senderAlreadyPresent = emailsPySource.includes(senderMarker);
  if (senderAlreadyPresent && !options.force) {
    throw new EmailGeneratorError(
      `${rel(repo, emailsPyPath)} already defines ${senderMarker}...). Pass --force to append ` +
        `another copy, or pick a different name. Nothing was written.`,
    );
  }

  const inserts = buildInserts(names, options.subject, tokens);
  const source = fs.readFileSync(templatePath, "utf8");
  const contents = render(source, { names, flags: new Set(), inserts }, rel(repo, templatePath));

  const plan = new Plan();
  plan.add(destTemplate, contents);

  if (senderAlreadyPresent) {
    plan.skip(
      emailsPyPath,
      `already defines ${senderMarker}...) — appending another under --force`,
    );
  }
  const newEmailsPySource =
    emailsPySource + senderLines(names, options.subject, tokens).join("\n") + "\n";
  plan.add(emailsPyPath, newEmailsPySource);

  if (options.dryRun) {
    reportPlan(repo, plan, true);
    console.log("\n--dry-run: nothing was written.");
    return 0;
  }

  plan.write();

  const formattedTs = formatTs(repo, [destTemplate]);
  if (!formattedTs.ok) plan.note(`  note: ${formattedTs.message}`);
  const formattedPy = formatPython(repo, [emailsPyPath]);
  if (!formattedPy.ok) plan.note(`  note: ${formattedPy.message}`);

  reportPlan(repo, plan, false);
  plan.note("");
  console.log(
    `\nNext, and not done for you:\n` +
      `  - write the body copy in ${rel(repo, destTemplate)} — see ` +
      `packages/emails/templates/invitation.tsx for the shape\n` +
      `  - run \`pnpm --filter @keel/emails build\` before sending or testing this email\n` +
      `  - dispatch send_${names.resource}_email from the owning service via a Tier-1 task ` +
      `(keel.core.tasks), on transaction.on_commit() — never call it inside an open transaction ` +
      `(.claude/commands/new-email.md)\n` +
      `  - route that task through the "email" queue`,
  );
  return 0;
}
