import { defineConfig, devices } from "@playwright/test";

// The app is built against a fake API origin; every API call is fulfilled from
// tests/fixtures by e2e/mock.ts, so e2e runs need no backend.
export const API = "http://api.finn.test";
const PORT = 3100;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    ...devices["iPhone 13"],
    browserName: "chromium",
    viewport: { width: 390, height: 844 },
    trace: "retain-on-failure",
    // page.route can't see requests a service worker makes; tests that need the worker opt back in
    serviceWorkers: "block",
  },
  webServer: {
    command: `NEXT_PUBLIC_API_URL=${API} npx next build && npx next start -p ${PORT}`,
    url: `http://localhost:${PORT}`,
    timeout: 240_000,
    reuseExistingServer: !process.env.CI,
  },
});
