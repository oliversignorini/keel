import { defineConfig } from "orval";

// The merged document (../../openapi.merged.json, built by
// scripts/merge_openapi.py from the live drf-spectacular + allauth headless
// schemas — see that script's docstring) landed with p3-orgs-api, replacing
// the hand-authored allauth-only stand-in this file used to point at.
// Everything — allauth's own endpoints and organizations/permissions.py's
// endpoints (PRD §7) — is one input now, generated into the same two files
// this package already had, so nothing downstream that imports from
// `identity.query`/`identity.zod` has to change import paths.
//
// This has to stay ONE orval output pair rather than two tag-filtered
// ones: `mode: "single"` dumps every `components/schemas` entry into each
// output file regardless of `filters.tags` (the filter only trims which
// *operations* are generated), so two outputs from the same spec produce
// ~200 duplicate type exports that collide the moment both are re-exported
// from src/index.ts. One output has no such collision because there is
// only one copy of each type to begin with.
const input = { target: "../../openapi.merged.json" };

// A single "react-query" output already includes the plain fetch functions
// and the generated types alongside the hooks, so one output covers B.1's
// "typed fetch functions, TanStack Query hooks and Zod schemas" — a second
// fetch-only output would just duplicate every name and collide on export.
export default defineConfig({
  identityQuery: {
    input,
    output: {
      mode: "single",
      target: "./src/generated/identity.query.ts",
      client: "react-query",
      httpClient: "fetch",
      baseUrl: "",
      mock: false,
      override: {
        mutator: {
          path: "./src/http/mutator.ts",
          name: "identityFetch",
        },
      },
    },
  },
  identityZod: {
    input,
    output: {
      mode: "single",
      target: "./src/generated/identity.zod.ts",
      client: "zod",
    },
  },
});
