import react from "@vitejs/plugin-react";
import path from "node:path";
import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Mirrors tsconfig.json's "@/*" path alias, which Next.js resolves at
    // build time but Vitest (a separate Vite instance) needs told about
    // explicitly — org-context.tsx, can.tsx etc. all import via "@/...".
    alias: {
      "@": path.resolve(__dirname, "."),
      // Mirrors tsconfig.json's "content-collections" path alias to the
      // generated output of content-collections.ts (apps/web/lib/blog).
      "content-collections": path.resolve(__dirname, ".content-collections/generated"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // e2e/ is Playwright's (playwright.config.ts), not Vitest's.
    exclude: [...configDefaults.exclude, "e2e/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
    },
  },
});
