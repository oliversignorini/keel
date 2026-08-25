import { defineConfig } from "orval";

// Input is a hand-authored stand-in until the p2-auth-api worktree lands the
// merged OpenAPI document (allauth's /_allauth/openapi.json + drf-spectacular's
// /api/v1/schema/). Swap `input.target` for the merged spec then re-run
// `pnpm generate` — src/generated is the only thing that changes.
const input = { target: "./openapi/allauth.v1.json" };

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
