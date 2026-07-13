import { chromium } from "playwright";

const baseUrl = process.env.COMFYUI_URL;

if (!baseUrl) {
  console.error("Set COMFYUI_URL to your running ComfyUI address before using this smoke test.");
  process.exit(1);
}

const headless = process.env.PLAYWRIGHT_HEADLESS !== "0";
const browser = await chromium.launch({ headless });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

try {
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });

  // Open Modal Studio via sidebar
  const sidebarEntry = page.getByText("Modal GPU", { exact: false }).first();
  await sidebarEntry.waitFor({ timeout: 15000 });
  await sidebarEntry.click();

  // Click the Open Studio button
  const openButton = page.getByRole("button", { name: /Open Studio/i }).first();
  await openButton.waitFor({ timeout: 10000 });
  await openButton.click();

  // Verify all four studio tabs are present
  await page.getByText("Playground", { exact: true }).waitFor({ timeout: 10000 });
  await page.getByText("History", { exact: true }).waitFor({ timeout: 10000 });
  await page.getByText("Backend", { exact: true }).waitFor({ timeout: 10000 });
  await page.getByText("Settings", { exact: true }).waitFor({ timeout: 10000 });

  // Click each tab and verify its content area loads
  await page.getByText("Playground", { exact: true }).click();

  await page.getByText("History", { exact: true }).click();
  await page.getByText("Run History", { exact: true }).waitFor({ timeout: 10000 });

  await page.getByText("Backend", { exact: true }).click();

  await page.getByText("Settings", { exact: true }).click();
  await page.getByText("Connection & credentials", { exact: false }).waitFor({ timeout: 10000 });

  // Close the modal, verify it disappears, then reopen
  await page.locator(".comfymodal-testing-close").click();
  await page.locator(".comfymodal-testing-close").waitFor({ state: "hidden", timeout: 10000 });
  await openButton.click();
  await page.getByText("Playground", { exact: true }).waitFor({ timeout: 10000 });

  // Reload to verify state recovery
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByText("Modal GPU", { exact: false }).first().waitFor({ timeout: 15000 });
} finally {
  await browser.close();
}
