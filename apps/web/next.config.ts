import { withContentCollections } from "@content-collections/next";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // @keel/ui ships TSX source, no build step of its own (a plain internal
  // workspace package) — Next transpiles it as part of this app's build.
  transpilePackages: ["@keel/ui"],
};

// Wires apps/web/content-collections.ts into the Next.js build (phase-7.md
// 7.4). Removing the marketing route group (PRD §8 Phase 9) means dropping
// this wrapper too — see docs/marketing-removal.md.
export default withContentCollections(nextConfig);
