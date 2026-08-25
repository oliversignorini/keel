import { z } from "zod";

/** Typed frontmatter for MDX blog posts (phase-7.md 7.4). Kept out of
 * content-collections.ts, which also imports @content-collections/mdx —
 * that pulls in esbuild, which breaks under Vitest's jsdom environment
 * (see content-collections.test.ts). */
export const postFrontmatterSchema = z.object({
  title: z.string(),
  description: z.string(),
  /** ISO 8601 date, e.g. "2026-01-15". */
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "date must be an ISO date (YYYY-MM-DD)"),
  author: z.string(),
  content: z.string(),
});
