// Modal Studio — Phase I8: Playground accessibility, loading, empty-state
// and copy polish (fake backend, deterministic).
//
// Pins the I8 lane contract against the running product:
//   A. Accessible page h2 + frozen Backend copy + real ellipsis / zero mojibake.
//   B. Page/section loading states use the shared I3 primitive
//      (role="status", aria-live="polite") while <select> placeholders remain
//      textual <option> control states — held-route deterministic.
//   C. Recent-run carousel accessible names are unique and context-bearing;
//      the EXP identity badge carries shared chip geometry with meta tone.
//   D. Cleared recent-runs is a generic empty state (no alert semantics).
//   E. Single Run stays on the frozen V2 transport seam (POST /studio/run).
//   F. Experiment state: matrix empty via shared primitive; submission hits
//      ONLY POST /studio/experiment-v2; cell status chips carry cm-chip +
//      truthful data-tone.
//
// No real Modal is invoked; everything runs against the deterministic fake.

import { test, expect } from "@playwright/test";
import {
  setupFakeTest,
  selectPreset,
  submitSingleRun,
  enableExperimentMode,
} from "./helpers.mjs";

const SEEDED_PRESET_ID = "preset_default";
const WF_SELECTOR = '[data-testid="workflow-selector"]';
const SUBMIT_BTN = '[data-testid="modern-experiment-submit-btn"]';
const ITEM = ".comfymodal-studio-carousel-item";
const EXP_ITEM = ".comfymodal-studio-carousel-item-experiment";

function trackExperimentRoutes(page) {
  const buckets = { v2CreatePosts: [], legacyCreatorPosts: [] };
  page.on("request", (request) => {
    const url = request.url();
    if (request.method() !== "POST") return;
    if (/\/comfymodal\/studio\/experiment-v2$/.test(url)) buckets.v2CreatePosts.push(url);
    if (/\/comfymodal\/studio\/experiment$/.test(url)) buckets.legacyCreatorPosts.push(url);
  });
  return buckets;
}

test.describe("Phase I8 playground polish", () => {
  test("A. page h2, frozen Backend copy, real ellipsis, no mojibake", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      // Visually-hidden accessible page heading under the shell h1.
      const h2 = page.locator('[data-testid="playground-page-title"]');
      await h2.waitFor({ state: "attached", timeout: 15000 });
      expect(await h2.evaluate((el) => el.tagName)).toBe("H2");
      await expect(h2).toHaveText("Playground");
      const hidden = await h2.evaluate((el) => {
        const cs = getComputedStyle(el);
        return cs.position === "absolute" && cs.visibility !== "hidden" && cs.display !== "none";
      });
      expect(hidden).toBe(true);

      // Fresh session selects no preset → controls prompt carries the
      // frozen wording.
      const link = page.locator("a", { hasText: "Open Backend to create presets" }).first();
      await expect(link).toBeVisible({ timeout: 15000 });

      // Real Unicode ellipsis in the loaded backend select placeholder…
      const select = page.locator('[data-testid="backend-select"]');
      await expect(select).toBeEnabled({ timeout: 15000 });
      const optionTexts = await select.locator("option").evaluateAll((els) =>
        els.map((o) => o.textContent)
      );
      expect(optionTexts).toContain("Select a backend…");

      // …and zero double-encoded sequences anywhere on the page.
      const pageText = await page.locator(".comfymodal-studio-pagecontainer").textContent();
      expect(pageText).not.toContain("\u00e2\u20ac");
      expect(pageText).not.toContain("Go to Backend tab to create presets");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("B. section loading uses role=status primitive; select option stays textual", async ({ page }) => {
    let releasePresets;
    const presetsGate = new Promise((resolve) => { releasePresets = resolve; });
    let releaseFeed;
    const feedGate = new Promise((resolve) => { releaseFeed = resolve; });

    await page.route("**/comfymodal/studio/presets*", async (route) => {
      await presetsGate;
      await route.continue();
    });
    await page.route("**/comfymodal/history-v2/feed*", async (route) => {
      await feedGate;
      await route.continue();
    });

    const fx = await setupFakeTest(page);
    try {
      // Capabilities section loading state: shared primitive semantics.
      const capsLoading = page.locator('[data-testid="playground-capabilities-loading"]');
      await expect(capsLoading).toBeVisible({ timeout: 15000 });
      await expect(capsLoading).toHaveAttribute("role", "status");
      await expect(capsLoading).toHaveAttribute("aria-live", "polite");
      await expect(capsLoading).toContainText("Loading preset capabilities…");

      // Control-specific loading remains an honest <option> inside the
      // disabled select — NOT a div primitive inside <select>.
      const opt = page.locator('[data-testid="backend-select"] option').first();
      await expect(opt).toHaveText("Loading backends…");
      expect(await opt.getAttribute("disabled")).not.toBeNull();

      // Recent runs loading state: shared primitive as well.
      const runsLoading = page.locator('[data-testid="playground-recent-runs-loading"]');
      await expect(runsLoading).toBeVisible({ timeout: 15000 });
      await expect(runsLoading).toHaveAttribute("role", "status");
      await expect(runsLoading).toContainText("Loading recent runs…");

      // Release the held fetches; loading primitives are replaced by data.
      releasePresets();
      releaseFeed();
      await expect(page.locator('[data-testid="backend-select"] option').first())
        .toHaveText("Select a backend…", { timeout: 20000 });
      await expect(page.locator('[data-testid="playground-capabilities-loading"]')).toHaveCount(0);
      await expect(page.locator(ITEM).first()).toBeVisible({ timeout: 20000 });
      fx.assertNoConsoleErrors();
    } finally {
      releasePresets();
      releaseFeed();
      await page.unroute("**/comfymodal/studio/presets*");
      await page.unroute("**/comfymodal/history-v2/feed*");
      fx.guard.dispose();
    }
  });

  test("C. carousel accessible names unique + EXP badge shared meta chip geometry", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await expect(page.locator(ITEM).first()).toBeVisible({ timeout: 20000 });

      const labels = await page.locator(ITEM).evaluateAll((els) =>
        els.map((el) => el.getAttribute("aria-label"))
      );
      expect(labels.length).toBeGreaterThanOrEqual(2);

      // Every name is context-bearing (status + time) and ends with a
      // truthful call to action; none uses the old generic text.
      for (const name of labels) {
        expect(name).toMatch(/, .+ at \d{1,2}:\d{2} (AM|PM)\. (Open run\.|Open experiment\.|No image\.)$/);
        expect(name).not.toContain("Click to view");
        expect(name).not.toMatch(/[0-9a-f]{16,}/i);
      }

      // Uniqueness across all visible items (the I1 defect).
      expect(new Set(labels).size).toBe(labels.length);

      // The EXP identity badge rides the shared chip geometry with the
      // muted meta tone (informational — never a status/error look).
      const expBadge = page.locator(EXP_ITEM).first().locator(".comfymodal-studio-carousel-exp-badge");
      await expect(expBadge).toBeVisible({ timeout: 10000 });
      await expect(expBadge).toHaveText("EXP");
      expect(await expBadge.getAttribute("data-tone")).toBe("meta");
      expect(await expBadge.getAttribute("aria-hidden")).toBe("true");
      const geo = await expBadge.evaluate((el) => {
        const cs = getComputedStyle(el);
        return { radius: cs.borderRadius, display: cs.display, fontSize: cs.fontSize, padding: cs.padding };
      });
      // Shared .cm-chip geometry (absolute positioning blockifies
      // inline-flex → flex; radius/padding/typography prove the base).
      expect(["inline-flex", "flex"]).toContain(geo.display);
      expect(geo.radius).toBe("999px");
      expect(geo.fontSize).toBe("10px");
      expect(geo.padding).toBe("2px 8px");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("D. cleared recent runs render the generic empty-state primitive", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await expect(page.locator(ITEM).first()).toBeVisible({ timeout: 20000 });

      await page.locator(".comfymodal-studio-carousel-btn.danger").click();

      const cleared = page.locator('[data-testid="playground-recent-runs-cleared"]');
      await expect(cleared).toBeVisible({ timeout: 15000 });
      expect(await cleared.evaluate((el) => el.classList.contains("cm-empty-state"))).toBe(true);
      await expect(cleared).toContainText("Recent runs cleared.");
      await expect(cleared).toContainText("Submit a new run to see results here.");

      // An empty state is normal application state: no alert/live semantics.
      expect(await cleared.getAttribute("role")).toBeNull();
      expect(await cleared.getAttribute("aria-live")).toBeNull();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("E. single Run remains on the V2 execution path end-to-end", async ({ page }) => {
    const runPostUrls = [];
    const onRequest = (request) => {
      if (
        request.method() === "POST"
        && /\/comfymodal\/studio\/run$/.test(request.url())
      ) {
        runPostUrls.push(request.url());
      }
    };
    page.on("request", onRequest);

    const fx = await setupFakeTest(page);
    try {
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);
      await fx.waitForStatus("Run completed", { timeout: 25000 });

      // Frozen transport seam used exactly once for this single run.
      expect(runPostUrls.length).toBe(1);
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 20000 });
      fx.assertNoConsoleErrors();
    } finally {
      page.off("request", onRequest);
      fx.guard.dispose();
    }
  });

  test("F. experiment state: matrix empty primitive, V2-only creator, toned cell chips", async ({ page }) => {
    const tracker = trackExperimentRoutes(page);
    const fx = await setupFakeTest(page);
    try {
      // Selecting a workflow hydrates the modern experiment surface.
      await page.locator(WF_SELECTOR).selectOption("wf_text2img");
      await expect(page.locator('[data-testid="workflow-control-seed"]')).toBeVisible({ timeout: 10000 });
      await enableExperimentMode(page);

      // No axes/backends chosen yet → generic empty-state hint.
      const matrixEmpty = page.locator('[data-testid="experiment-matrix-empty"]');
      await expect(matrixEmpty).toBeVisible({ timeout: 10000 });
      expect(await matrixEmpty.evaluate((el) => el.classList.contains("cm-empty-state"))).toBe(true);

      // Submission goes through the modern V2 creator only.
      const btn = page.locator(SUBMIT_BTN);
      await expect(btn).toBeEnabled({ timeout: 10000 });
      await btn.click();
      await expect.poll(() => tracker.v2CreatePosts.length, { timeout: 10000 }).toBe(1);
      expect(tracker.legacyCreatorPosts).toEqual([]);

      // Cell status chips adopt the shared base with a truthful tone.
      const cellChip = page
        .locator('[data-testid="experiment-v2-grid"] [data-cell-id]')
        .first()
        .locator(".comfymodal-studio-history-v2-chip");
      await expect(cellChip).toBeVisible({ timeout: 15000 });
      const chipClass = await cellChip.evaluate((el) => el.className);
      expect(chipClass).toContain("cm-chip");
      expect(chipClass).toContain("status-queued");
      expect(await cellChip.getAttribute("data-tone")).toBe("running");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
