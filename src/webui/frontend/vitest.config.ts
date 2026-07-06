import { defineConfig } from "vitest/config";
import path from "node:path";

// Vitest config kept separate from vite.config.ts so the Vite build config stays
// pure Vite (Vite 8's UserConfig no longer accepts a `test` key inline). The
// palette-ranking unit tests are pure TS — a node environment is enough.
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
