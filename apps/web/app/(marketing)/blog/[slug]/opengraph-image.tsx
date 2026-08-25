import { ImageResponse } from "next/og";

import { allPosts } from "content-collections";

export const alt = "Keel blog post";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export function generateStaticParams() {
  return allPosts.map((post) => ({ slug: post.slug }));
}

export default async function OpengraphImage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const post = allPosts.find((candidate) => candidate.slug === slug);

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "80px",
          backgroundColor: "#171717",
          color: "#fafafa",
        }}
      >
        <div style={{ fontSize: 24, color: "#a3a3a3" }}>Keel blog</div>
        <div style={{ fontSize: 64, fontWeight: 600, marginTop: 16 }}>
          {post?.title ?? "Keel"}
        </div>
      </div>
    ),
    { ...size },
  );
}
