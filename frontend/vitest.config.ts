import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // Why: `e2e/*.spec.ts` are Playwright specs (run via `npm run test:e2e`).
    // Without this exclude, vitest picks them up and fails on the
    // `@playwright/test` imports.
    exclude: ["**/node_modules/**", "**/dist/**", "e2e/**"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
