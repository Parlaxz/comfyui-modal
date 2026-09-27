// I1 AUDIT-ONLY SPEC — NOT registered in the deterministic gate.
// Purpose: Phase-I1 product-polish reconnaissance evidence collection.
// Produces screenshots + audit.json under reports/phase-i1-artifacts/.
// Read-only against production code; no assertions about product behavior
// beyond soft evidence collection (failures are recorded, not thrown,
// except hard harness failures).

import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { setupFakeTest, seedHistory } from "./helpers.mjs";

const ART_DIR = path.resolve("reports/phase-i1-artifacts");
const PAGES = ["playground", "history", "workflows", "backend", "settings"];
const VIEWPORTS = [
  [1440, 900],
  [1024, 768],
  [768, 900],
  [480, 800],
];

function dumpPageStructure() {
  return {
    headings: Array.from(
      document.querySelectorAll('[data-testid="studio-page"] h1, [data-testid="studio-page"] h2, [data-testid="studio-page"] h3, [data-testid="studio-page"] h4, [data-testid="studio-page"] h5, [data-testid="studio-page"] h6')
    ).map((h) => ({ level: h.tagName.toLowerCase(), text: h.textContent.trim().slice(0, 80) })),
    nav: Array.from(document.querySelectorAll(".comfymodal-studio-topnav > *")).map((n) => ({
      tag: n.tagName.toLowerCase(),
      text: n.textContent.trim(),
      dataPage: n.getAttribute("data-page"),
      ariaCurrent: n.getAttribute("aria-current"),
      className: n.className,
    })),
    navElementTag: document.querySelector(".comfymodal-studio-topnav")?.tagName.toLowerCase(),
    navRole: document.querySelector(".comfymodal-studio-topnav")?.getAttribute("role"),
    chipClasses: (() => {
      const counts = {};
      document.querySelectorAll('[data-testid="studio-page"] [class*="badge"], [data-testid="studio-page"] [class*="chip"], [data-testid="studio-page"] [class*="pill"], [data-testid="studio-page"] [class*="-tag"]').forEach((elx) => {
        elx.classList.forEach((c) => {
          if (/badge|chip|pill|-tag\b/.test(c)) counts[c] = (counts[c] || 0) + 1;
        });
      });
      return counts;
    })(),
    loadingTexts: (() => {
      const out = [];
      const walker = document.createTreeWalker(document.querySelector('[data-testid="studio-page"]'), NodeFilter.SHOW_TEXT);
      let n;
      while ((n = walker.nextNode())) {
        const t = n.textContent.trim();
        if (/^Loading|^Refreshing|Loading\.\.\.|Fetching/.test(t)) out.push(t.slice(0, 60));
      }
      return out;
    })(),
    buttonsWithoutName: Array.from(document.querySelectorAll('[data-testid="studio-page"] button')).filter((b) => {
      const label = (b.getAttribute("aria-label") || b.textContent || "").trim();
      return label.length === 0;
    }).map((b) => ({ cls: b.className.slice(0, 60), html: b.outerHTML.slice(0, 120) })),
    duplicateButtonNames: (() => {
      const names = {};
      document.querySelectorAll('[data-testid="studio-page"] button').forEach((b) => {
        const label = (b.getAttribute("aria-label") || b.textContent || "").trim().replace(/\s+/g, " ");
        if (label) names[label] = (names[label] || 0) + 1;
      });
      return Object.fromEntries(Object.entries(names).filter(([, c]) => c > 3));
    })(),
    ariaExpandedCount: document.querySelectorAll('[data-testid="studio-page"] [aria-expanded]').length,
    roleAttrCount: document.querySelectorAll('[data-testid="studio-page"] [role]').length,
    clickableNonButtons: (() => {
      let count = 0;
      document.querySelectorAll('[data-testid="studio-page"] div, [data-testid="studio-page"] span').forEach((d) => {
        if (getComputedStyle(d).cursor === "pointer") count++;
      });
      return count;
    })(),
    horizontalOverflow: (() => {
      const se = document.scrollingElement;
      const pageEl = document.querySelector('[data-testid="studio-page"]');
      return {
        docOverflow: se.scrollWidth - se.clientWidth,
        pageOverflow: pageEl ? pageEl.scrollWidth - pageEl.clientWidth : null,
      };
    })(),
  };
}

async function keyboardWalk(page, steps) {
  const stops = [];
  for (let i = 0; i < steps; i++) {
    await page.keyboard.press("Tab");
    const d = await page.evaluate(() => {
      const a = document.activeElement;
      if (!a || a === document.body) return { tag: "body" };
      return {
        tag: a.tagName.toLowerCase(),
        cls: (a.className || "").toString().slice(0, 70),
        testid: a.getAttribute && a.getAttribute("data-testid"),
        text: (a.textContent || "").trim().slice(0, 40),
        page: a.closest && a.closest(".comfymodal-studio-topnav") ? "topnav" : "content",
      };
    });
    stops.push(d);
  }
  return stops;
}

test.describe.configure({ mode: "serial" });

test("I1 recon sweep: five pages x viewports + a11y + A/B targets", async ({ page }, testInfo) => {
  test.setTimeout(300000);
  fs.mkdirSync(ART_DIR, { recursive: true });
  const audit = { generatedAt: new Date().toISOString(), viewports: VIEWPORTS, pages: {}, keyboard: {}, historyDetail: {}, notes: [] };

  const fx = await setupFakeTest(page, {
    beforeMount: async ({ page: p, sessionId }) => {
      await seedHistory(p, sessionId, "history_v2_phase_e");
    },
  });

  // ── Per-viewport screenshots + overflow ──────────────────────────────
  for (const [w, h] of VIEWPORTS) {
    await page.setViewportSize({ width: w, height: h });
    for (const p of PAGES) {
      await fx.gotoPage(p);
      await page.waitForTimeout(400);
      const file = path.join(ART_DIR, `${p}-${w}.png`);
      await page.screenshot({ path: file, fullPage: false });
      audit.pages[p] = audit.pages[p] || {};
      audit.pages[p][`overflow_${w}`] = await page.evaluate(() => {
        const se = document.scrollingElement;
        const pe = document.querySelector('[data-testid="studio-page"]');
        return { doc: se.scrollWidth - se.clientWidth, page: pe ? pe.scrollWidth - pe.clientWidth : null };
      });
    }
  }

  // ── Structure dumps at 1440 ──────────────────────────────────────────
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const p of PAGES) {
    await fx.gotoPage(p);
    await page.waitForTimeout(500);
    audit.pages[p].structure = await page.evaluate(dumpPageStructure);
  }

  // ── Keyboard traversal on Playground ─────────────────────────────────
  await fx.gotoPage("playground");
  await page.waitForTimeout(400);
  await page.evaluate(() => { if (document.activeElement) document.activeElement.blur(); });
  audit.keyboard.playgroundTabStops = await keyboardWalk(page, 16);

  // Focus-visible on nav button via keyboard
  const navBtn = page.locator('.comfymodal-studio-topnav button[data-page="history"]');
  await navBtn.focus(); // programmatic; then simulate keyboard by checking :focus-visible via keyboard event path
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Tab");
  audit.keyboard.navButtonFocusVisible = await page.evaluate(() => {
    const b = document.querySelector('.comfymodal-studio-topnav button[data-page="history"]');
    const cs = getComputedStyle(b);
    return {
      matchesFocusVisible: b.matches(":focus-visible"),
      outlineStyle: cs.outlineStyle,
      outlineWidth: cs.outlineWidth,
      boxShadow: cs.boxShadow.slice(0, 80),
    };
  });
  await page.screenshot({ path: path.join(ART_DIR, "keyboard-nav-focus.png") });

  // ── History generation detail (A/B target candidate A) ───────────────
  try {
    await fx.gotoPage("history");
    await page.waitForTimeout(600);
    const card = page.locator('[data-testid="history-v2-generation-card"]').first();
    await card.waitFor({ state: "visible", timeout: 10000 });
    await card.click();
    const overlay = page.locator('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]');
    await overlay.waitFor({ state: "visible", timeout: 10000 });
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(ART_DIR, "history-generation-detail.png") });
    audit.historyDetail.generationOverlay = await page.evaluate(() => {
      const ov = document.querySelector('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]');
      if (!ov) return null;
      const imgs = Array.from(ov.querySelectorAll("img")).map((im) => ({
        src: (im.getAttribute("src") || "").slice(0, 90),
        alt: im.getAttribute("alt"),
        w: im.clientWidth,
        h: im.clientHeight,
      }));
      const btns = Array.from(ov.querySelectorAll("button")).map((b) => (b.getAttribute("aria-label") || b.textContent || "").trim().slice(0, 40)).slice(0, 40);
      return {
        role: ov.getAttribute("role"),
        ariaModal: ov.getAttribute("aria-modal"),
        imageCount: imgs.length,
        images: imgs.slice(0, 8),
        buttons: btns,
        hasZoomViewer: !!ov.querySelector(".comfymodal-studio-zoom-wrap"),
        headings: Array.from(ov.querySelectorAll("h1,h2,h3,h4")).map((x) => `${x.tagName}:${x.textContent.trim().slice(0, 50)}`),
      };
    });
    // focus inside overlay?
    audit.historyDetail.focusInsideOverlay = await page.evaluate(() => {
      const ov = document.querySelector('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]');
      return ov ? ov.contains(document.activeElement) : false;
    });
    // Escape behavior + focus restoration
    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);
    audit.historyDetail.afterEscape = await page.evaluate(() => ({
      overlayGone: !document.querySelector('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]'),
      activeElement: document.activeElement ? `${document.activeElement.tagName}.${(document.activeElement.className || "").toString().slice(0, 50)}` : "none",
    }));
  } catch (e) {
    audit.notes.push(`history generation detail failed: ${e.message}`);
  }

  // ── History experiment detail (A/B target candidate B) ───────────────
  try {
    await fx.gotoPage("history");
    await page.waitForTimeout(600);
    const expCard = page.locator('[data-testid="history-v2-experiment-card"]').first();
    if ((await expCard.count()) > 0) {
      await expCard.click();
      await page.waitForTimeout(700);
      await page.screenshot({ path: path.join(ART_DIR, "history-experiment-detail.png") });
      audit.historyDetail.experimentOverlay = await page.evaluate(() => {
        const ovs = Array.from(document.querySelectorAll(".comfymodal-studio-history-v2-overlay"));
        const ov = ovs[ovs.length - 1];
        if (!ov) return null;
        return {
          ariaLabel: ov.getAttribute("aria-label"),
          imageCount: ov.querySelectorAll("img").length,
          cellTiles: ov.querySelectorAll(".comfymodal-studio-experiment-grid-cell").length,
          headings: Array.from(ov.querySelectorAll("h1,h2,h3,h4")).map((x) => `${x.tagName}:${x.textContent.trim().slice(0, 50)}`),
        };
      });
      await page.keyboard.press("Escape");
      await page.waitForTimeout(300);
    } else {
      audit.notes.push("no experiment card present in phase_e seed view");
    }
  } catch (e) {
    audit.notes.push(`history experiment detail failed: ${e.message}`);
  }

  // ── Preview overlay via zoom viewer (shared image modal, A/B target C) ─
  try {
    await fx.gotoPage("history");
    await page.waitForTimeout(600);
    const card = page.locator('[data-testid="history-v2-generation-card"]').first();
    await card.click();
    const overlay = page.locator('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]');
    await overlay.waitFor({ state: "visible", timeout: 10000 });
    // Try clicking a served image / preview thumb to open the shared preview overlay
    const img = overlay.locator("img").first();
    if ((await img.count()) > 0) {
      await img.click({ force: true }).catch(() => {});
      await page.waitForTimeout(600);
      const previewOpen = await page.evaluate(() => !!document.querySelector(".comfymodal-studio-preview-overlay"));
      audit.historyDetail.sharedPreviewOverlayOpened = previewOpen;
      if (previewOpen) {
        await page.screenshot({ path: path.join(ART_DIR, "shared-image-preview-overlay.png") });
        audit.historyDetail.previewOverlayStructure = await page.evaluate(() => {
          const pv = document.querySelector(".comfymodal-studio-preview-overlay");
          return {
            role: pv.getAttribute("role"),
            ariaModal: pv.getAttribute("aria-modal"),
            ariaLabel: pv.getAttribute("aria-label"),
            toolbarButtons: Array.from(pv.querySelectorAll("button")).map((b) => b.getAttribute("aria-label") || b.textContent.trim()).slice(0, 12),
          };
        });
      }
    }
    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);
    await page.keyboard.press("Escape");
  } catch (e) {
    audit.notes.push(`shared preview overlay probe failed: ${e.message}`);
  }

  // ── Narrow viewport nav stress shot ──────────────────────────────────
  await page.setViewportSize({ width: 480, height: 800 });
  await fx.gotoPage("workflows");
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(ART_DIR, "narrow-nav-workflows-480.png") });

  fs.writeFileSync(path.join(ART_DIR, "audit.json"), JSON.stringify(audit, null, 2));
});
