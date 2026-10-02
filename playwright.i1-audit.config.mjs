// @ts-check
// I1 AUDIT-ONLY Playwright config — NOT part of the deterministic gate.
// Runs tests/browser/fake/i1-audit.spec.mjs against the same fake server.
import { defineConfig } from "@playwright/test";

const fakePort = Number(process.env.STUDIO_FAKE_PORT || 8377);
const fakeBaseURL = `http://127.0.0.1:${fakePort}`;

export default defineConfig({
  testDir: "tests/browser/fake",
  testMatch: /i1-audit\.spec\.mjs/,
  outputDir: "test-results/i1-audit",
  fullyParallel: false,
  workers: 1,
  timeout: 300000,
  retries: 0,
  reporter: [["line"]],
  use: {
    baseURL: fakeBaseURL,
    headless: true,
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  },
  webServer: {
    command: "node tests/browser/fake/fake-server.mjs",
    url: fakeBaseURL,
    reuseExistingServer: true,
    timeout: 30000,
  },
  projects: [{ name: "fake-chromium", use: { browserName: "chromium" } }],
});
