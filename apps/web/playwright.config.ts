import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  // Local runs query the complete ingested database; an unfiltered directory
  // page can take 20s on a cold national dataset. CI uses the small synthetic
  // demo, so it keeps tighter timeouts that still catch real regressions.
  timeout: process.env.CI ? 30_000 : 120_000,
  expect: { timeout: process.env.CI ? 5_000 : 15_000 },
  // One worker keeps the shared API rate limit and dynamic-render load deterministic.
  // The suite is small; parallel workers caused avoidable timeouts and 429s locally.
  workers: 1,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] } },
  ],
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        // CI starts the production build; local runs use the dev server for HMR.
        command: process.env.CI ? "pnpm start" : "pnpm dev",
        url: baseURL,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
