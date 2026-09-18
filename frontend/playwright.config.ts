import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  reporter: "line",
  use: {
    baseURL: process.env.SENTINELX_BROWSER_BASE_URL || "https://sentinelx-lac.vercel.app",
    browserName: "chromium",
    channel: process.env.CI ? undefined : "chrome",
    headless: true,
    trace: "retain-on-failure",
  },
});
