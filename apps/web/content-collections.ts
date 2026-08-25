import { defineCollection, defineConfig } from "@content-collections/core";
import { compileMDX } from "@content-collections/mdx";

import { postFrontmatterSchema } from "./lib/blog/post-schema";

/**
 * MDX blog posts (phase-7.md 7.4; PRD §5 "MDX via content-collections for
 * type-safe frontmatter"). Posts are files under content/blog, not a CMS
 * — a CMS is a per-project decision.
 *
 * A post with a missing or wrong-typed frontmatter field fails the build
 * here rather than rendering with `undefined` in its place — that's what
 * "typed frontmatter" buys over a hand-rolled gray-matter parse.
 */
const posts = defineCollection({
  name: "posts",
  directory: "content/blog",
  include: "*.mdx",
  schema: postFrontmatterSchema,
  transform: async (document, context) => {
    const mdx = await compileMDX(context, document);
    return {
      ...document,
      slug: document._meta.path,
      mdx,
    };
  },
});

export default defineConfig({
  content: [posts],
});
