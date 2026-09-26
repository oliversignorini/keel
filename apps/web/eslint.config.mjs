import { next } from "@keel/eslint-config/next";
import { plugin as shadcn } from "@shadcn/lint";

/** @type {import("eslint").Linter.Config[]} */
export default [
  ...next,
  {
    ignores: ["next-env.d.ts"],
  },
  // Design-system guard (software-factory profile): app code composes
  // @keel/ui components and theme tokens instead of restyling them or
  // reaching for raw colours / arbitrary values. packages/ui itself is
  // where components are defined, so it is not linted by these rules.
  {
    files: ["**/*.{js,jsx,ts,tsx}"],
    plugins: { shadcn },
    settings: {
      shadcn: {
        ui: "@keel/ui",
        note: "Use @keel/ui components and packages/ui/theme.css tokens; see AGENTS.md > Design system.",
      },
    },
    rules: {
      "shadcn/no-restyle": "error",
      "shadcn/no-raw-colors": "error",
      "shadcn/no-arbitrary-values": "error",
      "shadcn/no-inline-styles": "error",
      "shadcn/no-unknown-classes": "error",
      "shadcn/require-static-classes": "error",
    },
  },
];
