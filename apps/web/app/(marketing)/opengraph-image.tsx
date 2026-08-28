import { ImageResponse } from "next/og";

export const alt = "Keel — Django + Next.js SaaS template";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/** Shared Open Graph image for the landing and pricing pages. Blog posts
 * get their own, per-post version at blog/[slug]/opengraph-image.tsx. */
export default function OpengraphImage() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "#171717",
        color: "#fafafa",
      }}
    >
      <div style={{ fontSize: 96, fontWeight: 600 }}>Keel</div>
      <div style={{ fontSize: 32, marginTop: 16, color: "#a3a3a3" }}>
        Django + Next.js SaaS template
      </div>
    </div>,
    { ...size },
  );
}
