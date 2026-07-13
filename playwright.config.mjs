// @ts-check
import { defineConfig } from "@playwright/test";

const baseURL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";
const runId = process.env.PLAYWRIGHT_RUN_ID || String(process.pid);

export default defineConfig({
  testDir: "tests/browser",
  testMatch: /studio-.*\.spec\.mjs/,
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || `test-results/${runId}`,
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  retries: 0,
  reporter: [["html", { outputFolder: process.env.PLAYWRIGHT_REPORT_DIR || `playwright-report/${runId}`, open: "never" }]],

  expect: {
    timeout: 10000,
  },

  use: {
    baseURL,
    headless: process.env.PLAYWRIGHT_HEADLESS !== "0",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "mocked",
      testIgnore: /studio-live\.spec\.mjs/,
    },
    {
      name: "live",
      testMatch: /studio-live\.spec\.mjs/,
      workers: 1,
      timeout: Number(process.env.COMFYMODAL_LIVE_TIMEOUT_MS || 900000),
    },
  ],
});
