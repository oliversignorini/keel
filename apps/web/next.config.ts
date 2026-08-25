import { withContentCollections } from "@content-collections/next";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {};

// Wires apps/web/content-collections.ts into the Next.js build (phase-7.md
// 7.4). Removing the marketing route group (PRD §8 Phase 9) means dropping
// this wrapper too — see docs/marketing-removal.md.
export default withContentCollections(nextConfig);
