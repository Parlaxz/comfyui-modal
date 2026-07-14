// @ts-check
import { fileURLToPath } from "node:url";
import path from "node:path";
import { defineConfig } from "@playwright/test";

const __filename = fileURLToPath(import.meta.url);
const __pluginRoot = path.dirname(__filename);
const __comfyuiRoot = path.resolve(__pluginRoot, "..", "..");
const __defaultDataRoot = process.env.COMFYMODAL_LOCAL_DATA_DIR
  || path.resolve(__comfyuiRoot, "comfymodal-data");

const baseURL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";
const runId = process.env.PLAYWRIGHT_RUN_ID || String(process.pid);

/** Resolve a relative playwright output path under the external data root. */
function dataRootPath(...segments) {
  return path.resolve(__defaultDataRoot, ...segments);
}

const defaultOutputDir = dataRootPath("playwright", "test-results", runId);
const defaultReportDir = dataRootPath("playwright", "report", runId);

// Support explicit env overrides for tracing: off|on|retain-on-failure|on-first-retry
const traceMode = process.env.PLAYWRIGHT_TRACE || "retain-on-failure";

export default defineConfig({
  testDir: "tests/browser",
  testMatch: /studio-.*\.spec\.mjs/,
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || defaultOutputDir,
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  retries: 0,
  reporter: [["html", { outputFolder: process.env.PLAYWRIGHT_REPORT_DIR || defaultReportDir, open: "never" }]],

  expect: {
    timeout: 10000,
  },

  use: {
    baseURL,
    headless: process.env.PLAYWRIGHT_HEADLESS !== "0",
    viewport: { width: 1440, height: 900 },
    trace: traceMode,
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
