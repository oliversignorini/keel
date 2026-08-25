import nextPlugin from "@next/eslint-plugin-next";

import { base } from "./base.mjs";

/** @type {import("eslint").Linter.Config[]} */
export const next = [
  ...base,
  {
    plugins: {
      "@next/next": nextPlugin,
    },
    rules: {
      ...nextPlugin.configs.recommended.rules,
      ...nextPlugin.configs["core-web-vitals"].rules,
    },
  },
];

export default next;
