import { next } from "@keel/eslint-config/next";

/** @type {import("eslint").Linter.Config[]} */
export default [
  ...next,
  {
    ignores: ["next-env.d.ts"],
  },
];
