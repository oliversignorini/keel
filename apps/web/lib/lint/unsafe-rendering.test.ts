// Proves the `no-restricted-syntax` guardrail in
// packages/eslint-config/base.mjs (docs/boundary-guardrails.md "Unsafe
// rendering") actually fires on `dangerouslySetInnerHTML`, and that the
// documented escape hatch — an `eslint-disable-next-line` with a `--
// reason` — silences it. Lints in-memory source rather than a fixture
// file so a deliberate violation never has to live in the tree it also
// has to fail in.

import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

import { base } from "@keel/eslint-config";

const UNJUSTIFIED = `
export function Bad({ html }: { html: string }) {
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}
`;

const JUSTIFIED = `
export function Good({ html }: { html: string }) {
  // eslint-disable-next-line no-restricted-syntax -- deliberately-safe fixture for the guardrail test.
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}
`;

async function lint(code: string) {
  const eslint = new ESLint({
    overrideConfigFile: true,
    baseConfig: base,
    // no-restricted-syntax is a JS/TS-agnostic AST selector rule; parsing
    // as .tsx is enough to exercise it without pulling in the Next.js
    // plugin config this package doesn't own.
    overrideConfig: { languageOptions: { parserOptions: { ecmaFeatures: { jsx: true } } } },
  });
  return eslint.lintText(code, { filePath: "fixture.tsx" });
}

describe("no-restricted-syntax: dangerouslySetInnerHTML", () => {
  it("fails a deliberate, unjustified use", async () => {
    const results = await lint(UNJUSTIFIED);
    const [result] = results;
    expect(result).toBeDefined();
    const messages = result!.messages.filter((m) => m.ruleId === "no-restricted-syntax");
    expect(messages).toHaveLength(1);
    expect(messages[0]?.message).toContain("dangerouslySetInnerHTML");
  });

  it("passes the same use once justified via the documented escape hatch", async () => {
    const results = await lint(JUSTIFIED);
    const [result] = results;
    expect(result).toBeDefined();
    const messages = result!.messages.filter((m) => m.ruleId === "no-restricted-syntax");
    expect(messages).toHaveLength(0);
  });
});
