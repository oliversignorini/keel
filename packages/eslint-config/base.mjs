import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import tseslint from "typescript-eslint";

/** @type {import("eslint").Linter.Config[]} */
export const base = [
  js.configs.recommended,
  ...tseslint.configs.recommended,
  prettier,
  {
    ignores: ["**/.next/**", "**/dist/**", "**/node_modules/**", "**/.turbo/**", "**/coverage/**"],
  },
  {
    rules: {
      // docs/boundary-guardrails.md "Unsafe rendering": dangerouslySetInnerHTML
      // is an XSS surface the moment its input isn't fixed at render time.
      // The one legitimate use in this repo (components/json-ld.tsx) is a
      // server component rendering JSON.stringify'd, non-user data — it
      // passes via the standard eslint-disable-next-line escape hatch, with
      // a `-- reason` justification required alongside it.
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message:
            "dangerouslySetInnerHTML is an XSS surface. If this use is genuinely safe (fixed, non-user data), " +
            "justify it with `// eslint-disable-next-line no-restricted-syntax -- <reason>` on the line above. " +
            "If you're rendering user- or externally-supplied HTML/Markdown, it must go through a sanitizer first.",
        },
      ],
    },
  },
];

export default base;
