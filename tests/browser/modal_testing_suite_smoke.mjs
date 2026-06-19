import { chromium } from "playwright";

const baseUrl = process.env.COMFYUI_URL;

if (!baseUrl) {
  console.error("Set COMFYUI_URL to your running ComfyUI address before using this smoke test.");
  process.exit(1);
}

const browser = await chromium.launch({ headless: false });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

try {
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(4000);

  const sidebarEntry = page.getByText("Modal Testing", { exact: false }).first();
  await sidebarEntry.waitFor({ timeout: 15000 });
  await sidebarEntry.click();

  const openButton = page.getByRole("button", { name: /Open Testing Suite/i }).first();
  await openButton.waitFor({ timeout: 10000 });
  await openButton.click();

  await page.getByText("Dashboard", { exact: true }).waitFor({ timeout: 10000 });
  await page.getByText("Setup", { exact: true }).waitFor({ timeout: 10000 });
  await page.getByText("Results", { exact: true }).waitFor({ timeout: 10000 });
  await page.getByText("History", { exact: true }).waitFor({ timeout: 10000 });
  await page.getByText("Settings", { exact: true }).waitFor({ timeout: 10000 });

  await page.getByText("Setup", { exact: true }).click();
  await page.getByText("Workflows & Models", { exact: true }).waitFor({ timeout: 10000 });

  await page.getByText("Results", { exact: true }).click();
  await page.getByText("Progress", { exact: true }).waitFor({ timeout: 10000 });

  await page.getByText("History", { exact: true }).click();
  await page.getByText("Run History", { exact: true }).waitFor({ timeout: 10000 });

  await page.getByText("Settings", { exact: true }).click();
  await page.getByText("Connection & credentials", { exact: false }).waitFor({ timeout: 10000 });

  await page.getByRole("button", { name: "✕" }).click();
  await openButton.click();
  await page.getByText("Dashboard", { exact: true }).waitFor({ timeout: 10000 });

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(4000);
  await page.getByText("Modal Testing", { exact: false }).first().waitFor({ timeout: 15000 });
} finally {
  await browser.close();
}
