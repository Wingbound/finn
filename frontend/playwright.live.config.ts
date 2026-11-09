import { defineConfig, devices } from "@playwright/test";

// Checks against the deployed site, real API, no mocks:
//   LIVE_URL=https://finn-qx98.vercel.app npx playwright test -c playwright.live.config.ts
// LIVE_API=<api url> adds the /health check. LIVE_BUILD=SYMBOL also builds a dossier for SYMBOL
// through the UI (about 9 model calls).
export default defineConfig({
  testDir: "./e2e-live",
  reporter: [["list"]],
  timeout: 240_000,
  use: {
    baseURL: process.env.LIVE_URL,
    ...devices["iPhone 13"],
    browserName: "chromium",
    viewport: { width: 390, height: 844 },
    trace: "retain-on-failure",
  },
});
