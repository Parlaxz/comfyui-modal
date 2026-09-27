#!/usr/bin/env node
// Runtime inventory: enumerate interactive elements on each page via Playwright against fake backend
import { chromium } from "playwright";
import http from "node:http";
import { writeFileSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const fakePort = 8379; // avoid collision with other tests on 8377
process.env.STUDIO_FAKE_PORT = String(fakePort);

// Start fake server
const fakeServerPath = path.resolve(__dirname, "../../tests/browser/fake/fake-server.mjs");
console.log("Starting fake server from", fakeServerPath);

// We spawn the fake server as a subprocess
import { spawn } from "node:child_process";
const serverProc = spawn("node", [fakeServerPath], {
  env: { ...process.env, STUDIO_FAKE_PORT: String(fakePort) },
  stdio: ["ignore", "pipe", "pipe"],
});
let serverReady = false;
serverProc.stdout.on("data", (d) => {
  const s = String(d);
  if (s.includes("listening") || s.includes(String(fakePort))) serverReady = true;
  //console.log("[fake-server]", s.trim());
});
serverProc.stderr.on("data", (d) => console.error("[fake-server err]", String(d).trim()));

function waitForServer(url, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const tryFetch = () => {
      const req = http.get(url, (res) => {
        res.resume();
        resolve();
      });
      req.on("error", () => {
        if (Date.now() - start > timeoutMs) reject(new Error("server not ready timeout"));
        else setTimeout(tryFetch, 200);
      });
      req.end();
    };
    setTimeout(tryFetch, 500);
  });
}

async function enumeratePage(browser, pageName, extraSetup) {
  const context = await browser.newContext();
  const page = await context.newPage();
  // Create session
  const sessionRes = await page.request.post(`http://127.0.0.1:${fakePort}/__comfymodal_test/session`);
  const { sessionId } = await sessionRes.json();
  // Optional seed
  if (extraSetup) await extraSetup(page, sessionId);
  // Navigate to harness
  await page.goto(`http://127.0.0.1:${fakePort}/?session=${encodeURIComponent(sessionId)}`, { waitUntil: "domcontentloaded" });
  // Mount studio
  await page.waitForFunction(() => typeof window.__mountStudioForTest === "function", null, { timeout: 15000 });
  await page.evaluate(() => window.__mountStudioForTest());
  await page.waitForSelector('[data-testid="studio-page"]', { timeout: 15000 });
  // Navigate to desired page if not playground
  if (pageName !== "playground") {
    await page.evaluate((name) => {
      if (window.__studioApi && typeof window.__studioApi.setPage === "function") window.__studioApi.setPage(name);
    }, pageName);
    await page.waitForTimeout(500);
  }
  // Give time for async renders
  await page.waitForTimeout(1500);

  // Enumerate interactive elements
  const controls = await page.evaluate(() => {
    const results = [];
    const interactiveSelector = 'button, a[href], input, select, textarea, [role="button"], [role="slider"], [tabindex="0"], [data-testid]';
    const seen = new Set();
    const els = document.querySelectorAll(interactiveSelector);
    for (const el of els) {
      // Skip hidden (display:none) unless it has data-testid (for test coverage)
      const style = window.getComputedStyle(el);
      const isHidden = style.display === "none" || style.visibility === "hidden";
      // Skip option elements
      if (el.tagName === "OPTION") continue;
      const rect = el.getBoundingClientRect();
      const isVisible = rect.width > 0 && rect.height > 0 && style.display !== "none";
      const role = el.getAttribute("role") || el.tagName.toLowerCase();
      const testid = el.getAttribute("data-testid") || "";
      const ariaLabel = el.getAttribute("aria-label") || "";
      const text = (el.textContent || "").trim().slice(0, 80);
      const page = document.querySelector(".comfymodal-studio-pagecontainer")?.textContent?.slice(0, 20) || "";
      const key = `${role}:${testid}:${text}:${ariaLabel}`;
      if (seen.has(key)) continue;
      seen.add(key);
      results.push({
        tag: el.tagName.toLowerCase(),
        role: role,
        testid: testid || null,
        ariaLabel: ariaLabel || null,
        text: text || null,
        disabled: el.disabled || el.getAttribute("aria-disabled") === "true" || el.hasAttribute("disabled"),
        visible: isVisible && !isHidden,
        hidden: isHidden,
        classes: (el.className || "").toString().slice(0, 120),
      });
    }
    // Also collect nav buttons specifically
    const navBtns = document.querySelectorAll(".comfymodal-studio-topnav button");
    const navInfo = Array.from(navBtns).map(b => ({
      tag: "button",
      role: "nav-button",
      testid: b.getAttribute("data-testid"),
      ariaLabel: b.getAttribute("aria-label"),
      text: (b.textContent || "").trim(),
      pageAttr: b.getAttribute("data-page"),
      ariaCurrent: b.getAttribute("aria-current"),
      active: b.classList.contains("active"),
    }));
    return { controls: results, nav: navInfo, url: window.location.href };
  });

  await context.close();
  return { page: pageName, extra: extraSetup ? "seeded" : "default", ...controls };
}

const pages = ["playground", "history", "workflows", "backend", "settings"];
const browser = await chromium.launch({ headless: true });
try {
  const baseUrl = `http://127.0.0.1:${fakePort}/`;
  await waitForServer(baseUrl);
  console.log("Server ready at", baseUrl);

  const all = [];
  for (const page of pages) {
    console.log("Enumerating", page, "...");
    const result = await enumeratePage(browser, page);
    all.push(result);
    console.log(`  ${page}: ${result.controls.length} controls, nav: ${result.nav.map(n=>n.pageAttr).join(",")}`);
  }
  // Also enumerate history with seeded data and detail open
  console.log("Enumerating history (seeded) ...");
  {
    const context = await browser.newContext();
    const pg = await context.newPage();
    const sRes = await pg.request.post(`http://127.0.0.1:${fakePort}/__comfymodal_test/session`);
    const { sessionId } = await sRes.json();
    await pg.request.post(`http://127.0.0.1:${fakePort}/__comfymodal_test/history-seed`, { data: { sessionId, scenario: "history_v2_phase_e" } });
    await pg.goto(`http://127.0.0.1:${fakePort}/?session=${encodeURIComponent(sessionId)}`, { waitUntil: "domcontentloaded" });
    await pg.waitForFunction(() => typeof window.__mountStudioForTest === "function", null, { timeout: 15000 });
    await pg.evaluate(() => window.__mountStudioForTest());
    await pg.waitForSelector('[data-testid="studio-page"]', { timeout: 15000 });
    await pg.evaluate(() => window.__studioApi.setPage("history"));
    await pg.waitForTimeout(1500);
    // Click first generation card to open detail
    const card = pg.locator('[data-testid="history-v2-card"]').first();
    if (await card.count() > 0) {
      await card.click();
      await pg.waitForTimeout(800);
    }
    const detailControls = await pg.evaluate(() => {
      const results = [];
      const els = document.querySelectorAll('button, [role="button"], [data-testid]');
      for (const el of els) {
        const style = window.getComputedStyle(el);
        if (style.display === "none") continue;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) continue;
        results.push({
          tag: el.tagName.toLowerCase(),
          testid: el.getAttribute("data-testid"),
          text: (el.textContent||"").trim().slice(0,60),
          ariaLabel: el.getAttribute("aria-label"),
          visible: true,
        });
      }
      return results;
    });
    all.push({ page: "history-detail", extra: "generation-detail", controls: detailControls, nav: [] });
    console.log(`  history-detail: ${detailControls.length} controls`);
    await context.close();
  }

  writeFileSync(path.join(__dirname, "runtime-control-inventory.json"), JSON.stringify(all, null, 2));
  console.log("\nWrote runtime-control-inventory.json with", all.length, "page snapshots");
  // Summary
  let total = 0;
  for (const p of all) total += p.controls.length;
  console.log("Total runtime controls:", total);
} finally {
  await browser.close();
  serverProc.kill();
}
