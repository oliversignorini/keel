import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import "@testing-library/jest-dom/vitest";

// app/sitemap.ts imports the generated "content-collections" module, which
// the content-collections build produces into .content-collections/ (and
// which `next dev` produces as a side effect — the reason a missing build
// passes locally and fails in CI). The directory is generated output and is
// gitignored, so a fresh clone, a fresh worktree and CI all start without it.
//
// Left alone, the symptom is a vite resolve error pointing at sitemap.ts
// rather than at the missing build step. Fail once, up front, with the
// command to run.
const setupDir = dirname(fileURLToPath(import.meta.url));
const generated = join(setupDir, ".content-collections", "generated");

if (!existsSync(generated)) {
  throw new Error(
    `Content collections have not been built: ${generated} is missing.\n` +
      "Run `pnpm --filter web content:build` from the repo root first.\n" +
      "Without it, any test touching app/sitemap.ts fails with a vite " +
      'resolve error for "content-collections" that points nowhere near the cause.',
  );
}
