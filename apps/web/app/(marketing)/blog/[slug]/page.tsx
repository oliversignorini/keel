import { MDXContent } from "@content-collections/mdx/react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { allPosts } from "content-collections";
import { JsonLd } from "@/components/json-ld";
import { SITE_URL } from "@/lib/site";

export function generateStaticParams() {
  return allPosts.map((post) => ({ slug: post.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const post = allPosts.find((candidate) => candidate.slug === slug);
  if (!post) return {};
  return { title: `${post.title} — Keel`, description: post.description };
}

export default async function BlogPostPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const post = allPosts.find((candidate) => candidate.slug === slug);
  if (!post) notFound();

  return (
    <main className="mx-auto max-w-3xl px-4 py-16">
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "BlogPosting",
          headline: post.title,
          description: post.description,
          datePublished: post.date,
          author: { "@type": "Organization", name: post.author },
          url: `${SITE_URL}/blog/${post.slug}`,
        }}
      />
      <article>
        <h1 className="text-3xl font-semibold text-neutral-900 dark:text-neutral-100">
          {post.title}
        </h1>
        <p className="mt-2 text-sm text-neutral-500 dark:text-neutral-400">
          {post.date} · {post.author}
        </p>
        <div className="mt-8 flex flex-col gap-4 text-neutral-700 dark:text-neutral-300 [&_h2]:mt-8 [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:text-neutral-900 dark:[&_h2]:text-neutral-100">
          <MDXContent code={post.mdx} />
        </div>
      </article>
    </main>
  );
}
