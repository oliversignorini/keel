import Link from "next/link";
import type { Metadata } from "next";

import { allPosts } from "content-collections";

export const metadata: Metadata = {
  title: "Blog — Keel",
};

export default function BlogIndexPage() {
  const posts = [...allPosts].sort((a, b) => b.date.localeCompare(a.date));

  return (
    <main className="mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-3xl font-semibold text-foreground">Blog</h1>
      <ul className="mt-8 flex flex-col gap-8">
        {posts.map((post) => (
          <li key={post.slug}>
            <Link href={`/blog/${post.slug}`} className="block">
              <h2 className="text-xl font-semibold text-foreground hover:underline">
                {post.title}
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {post.date} · {post.author}
              </p>
              <p className="mt-2 text-muted-foreground">{post.description}</p>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
