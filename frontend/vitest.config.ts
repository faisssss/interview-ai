import { defineConfig } from "vitest/config";

export default defineConfig({
  // Unit tests only; the Playwright end-to-end tests live in e2e/.
  test: { include: ["src/**/*.test.ts"] },
});
