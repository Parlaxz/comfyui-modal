// @ts-check
import { defineConfig } from "@playwright/test";

// Modal Studio — deterministic fake-backend Playwright config.
//
// Runs the studio-fake-*.spec.mjs suite in tests/browser/fake against the
// fake backend server (tests/browser/fake/fake-server.mjs).  Fully
// self-contained: the webServer entry boots the fake backend on
// STUDIO_FAKE_PORT (default 8377) — no live ComfyUI instance is needed.
//
// The existing playwright.config.mjs (live-ComfyUI suite) ignores
// tests/browser/fake/** via the mocked project's testIgnore, so this
// config and the default config can coexist.

const fakePort = Number(process.env.STUDIO_FAKE_PORT || 8377);
const fakeBaseURL = `http://127.0.0.1:${fakePort}`;

export default defineConfig({
  testDir: "tests/browser/fake",
  testMatch: /studio-fake-.*\.spec\.mjs/,
  outputDir: "test-results/fake",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  retries: 0,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "test-results/fake-report" }],
  ],

  expect: {
    timeout: 10000,
    toHaveScreenshot: { animations: "disabled" },
  },

  use: {
    baseURL: fakeBaseURL,
    headless: true,
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },

  webServer: {
    command: "node tests/browser/fake/fake-server.mjs",
    url: fakeBaseURL,
    reuseExistingServer: true,
    timeout: 30000,
  },

  // Chromium only — the fake backend exercises the same browser the live
  // suite uses; firefox/webkit are not part of this foundation.
  projects: [{ name: "fake-chromium", use: { browserName: "chromium" } }],
});
