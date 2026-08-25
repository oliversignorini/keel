// src/http is hand-written: the fetch wrapper, typed errors, and CSRF
// handling that every generated request function is wired through.
//
// Everything under src/generated is produced by `pnpm generate` (orval) —
// see orval.config.ts and openapi/allauth.v1.json — and must never be
// hand-edited. This barrel lives outside that directory precisely so it
// survives regeneration.
export * from "./http/errors";
export * from "./http/normalize-envelope";
export * from "./http/csrf";
export * from "./http/mutator";
// identity.query.ts is orval's "react-query" output: it already contains
// the plain fetch functions and request/response types alongside the
// TanStack Query hooks, so this one export covers all three.
export * from "./generated/identity.query";
export * as identitySchemas from "./generated/identity.zod";
