// Phase I5 — Lightweight A/B image compare (fake E2E).
//
// Permanent product coverage for the I5 contract over EXACTLY TWO existing
// images, client-side and transient:
//   A. generation detail entry: Compare visible only for a usable managed
//      image, correct A preselection in the compare tray
//   B. two-image compare: B filled via "Add to compare (B)", both images
//      loaded, divider authority defaults to 50
//   C. keyboard slider: ArrowRight/ArrowLeft ±5, Home/End, aria-valuenow
//   D. pointer drag/click drives the SAME single divider authority
//   E. replacement: a further eligible pick truthfully replaces B ("Replaces
//      B" hint), A stays stable
//   F. Escape closes the view AND clears the transient session; focus is
//      restored through stable re-resolution; the underlying History detail
//      remains valid
//   G. responsive: 768/480/360 — narrow stacked presentation ≤640px, no
//      document horizontal overflow, slider stays keyboard-operable
//   H. network proof: compare interactions cause ONLY normal image GETs for
//      A/B assets — zero POST/PATCH/writes/routes
//   I. retirement guard: no Comparison Profiles / Runner / old A/B module

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const OVERLAY = '.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]';
const COMPARE_MODULE = "/extensions/comfymodal-modal/studio-image-compare.js";

async function openGenerationDetail(page, id) {
  const card = page.locator(`[data-testid="history-v2-generation-card"][data-id="${id}"]`);
  await expect(card).toBeVisible({ timeout: 15000 });
  await card.click();
  const overlay = page.locator(OVERLAY);
  await expect(overlay).toBeVisible({ timeout: 10000 });
  await expect(overlay.locator(".comfymodal-studio-history-v2-run-line")).toBeVisible({
    timeout: 15000,
  });
  return overlay;
}

async function addOutputToCompare(page, outputIndex) {
  // One ⋯ button per rendered output thumb, in outputs[] order.
  await page
    .locator(OVERLAY)
    .locator(".comfymodal-studio-history-v2-menu-btn")
    .nth(outputIndex)
    .click();
  const item = page.locator(`[data-testid="history-v2-output-add-to-compare-${outputIndex}"]`);
  await expect(item).toBeVisible();
  await item.click();
}

async function openCompareView(page) {
  const openBtn = page.locator('[data-testid="cm-compare-open"]');
  await expect(openBtn).toBeEnabled();
  await openBtn.click();
  await expect(page.locator('[data-testid="cm-compare-overlay"]')).toBeVisible();
  await expect(page.locator('[data-testid="cm-compare-img-b"]')).toHaveAttribute("data-loaded", "true", {
    timeout: 15000,
  });
}

async function sliderValue(page) {
  return Number(
    await page.locator('[data-testid="cm-compare-slider"]').getAttribute("aria-valuenow")
  );
}

test.describe("I5 lightweight A/B image compare", () => {
  test("A. generation detail: Compare visible for usable image; correct A label; absent without an image", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("history");

      // A record WITHOUT any usable image exposes no Compare control.
      await openGenerationDetail(page, "gen_no_image");
      await expect(page.locator('[data-testid="history-v2-compare"]')).toHaveCount(0);
      await page.keyboard.press("Escape");
      await expect(page.locator(OVERLAY)).toHaveCount(0);

      // A usable managed image offers Compare; activating it preselects A.
      await openGenerationDetail(page, "gen_ok");
      const compareBtn = page.locator('[data-testid="history-v2-compare"]');
      await expect(compareBtn).toBeVisible();
      await compareBtn.click();

      const tray = page.locator('[data-testid="cm-compare-tray"]');
      await expect(tray).toBeVisible();
      await expect(tray).toHaveAttribute("role", "region");
      await expect(tray).toHaveAttribute("aria-label", "Image compare selection");
      await expect(page.locator('[data-testid="cm-compare-tray-a"]')).toHaveText(/^A: Preview/);
      await expect(page.locator('[data-testid="cm-compare-tray-b"]')).toHaveText("B: not chosen");
      await expect(page.locator('[data-testid="cm-compare-open"]')).toBeDisabled();
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("B. two-image compare: B fills via Add to compare (B); both images load; divider at 50", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("history");
      await openGenerationDetail(page, "gen_ok");
      await page.locator('[data-testid="history-v2-compare"]').click();
      // The session outlives the source detail pane while the tray is active…
      await page.keyboard.press("Escape");
      await expect(page.locator(OVERLAY)).toHaveCount(0);
      await expect(page.locator('[data-testid="cm-compare-tray"]')).toBeVisible();

      // …so B can be picked from another reachable History output.
      await openGenerationDetail(page, "gen_preview_only");
      await addOutputToCompare(page, 0);
      await expect(page.locator('[data-testid="cm-compare-tray-b"]')).toHaveText(/^B: Output 1/);

      await openCompareView(page);
      const dialog = page.locator('[data-testid="cm-compare-dialog"]');
      await expect(dialog).toHaveAttribute(
        "aria-label",
        "Image comparison: Preview versus Output 1"
      );
      for (const side of ["a", "b"]) {
        await expect(page.locator(`[data-testid="cm-compare-img-${side}"]`)).toHaveAttribute(
          "data-loaded",
          "true"
        );
        const natural = await page.locator(`[data-testid="cm-compare-img-${side}"]`).evaluate(
          (img) => img.naturalWidth > 0 && img.naturalHeight > 0
        );
        expect(natural, `image ${side} decoded`).toBe(true);
      }
      await expect(page.locator('[data-testid="cm-compare-label-a"]')).toHaveText("Preview");
      await expect(page.locator('[data-testid="cm-compare-label-b"]')).toHaveText("Output 1");
      await expect(page.locator('[data-testid="cm-compare-slider"]')).toHaveAttribute(
        "aria-valuemin",
        "0"
      );
      await expect(page.locator('[data-testid="cm-compare-slider"]')).toHaveAttribute(
        "aria-valuemax",
        "100"
      );
      expect(await sliderValue(page)).toBe(50);

      // Focus lands on the slider handle when the view opens.
      const focusedIsSlider = await page.evaluate(() => {
        const ae = document.activeElement;
        return !!ae && ae.getAttribute("data-testid") === "cm-compare-slider";
      });
      expect(focusedIsSlider, "slider handle receives initial focus").toBe(true);
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("C. keyboard: arrows ±5, Home/End, aria-valuenow tracks the single authority", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("history");
      await openGenerationDetail(page, "gen_multi");
      await page.locator('[data-testid="history-v2-compare"]').click();
      await addOutputToCompare(page, 1);
      await openCompareView(page);

      const slider = page.locator('[data-testid="cm-compare-slider"]');
      await expect(slider).toBeFocused();
      await page.keyboard.press("ArrowRight");
      expect(await sliderValue(page)).toBe(55);
      await expect(slider).toHaveAttribute("aria-valuenow", "55");
      await expect(slider).toHaveAttribute("aria-valuetext", "55% Output 2");

      await page.keyboard.press("ArrowLeft");
      expect(await sliderValue(page)).toBe(50);

      await page.keyboard.press("Home");
      expect(await sliderValue(page)).toBe(0);
      await expect(slider).toHaveAttribute("aria-valuenow", "0");

      await page.keyboard.press("End");
      expect(await sliderValue(page)).toBe(100);
      await expect(slider).toHaveAttribute("aria-valuenow", "100");

      // Clamped nudges never escape 0–100.
      await page.keyboard.press("ArrowRight");
      expect(await sliderValue(page)).toBe(100);
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("D. pointer click/drag updates the same single divider authority", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("history");
      await openGenerationDetail(page, "gen_multi");
      await page.locator('[data-testid="history-v2-compare"]').click();
      await addOutputToCompare(page, 0);
      await openCompareView(page);

      const stage = page.locator('[data-testid="cm-compare-stage"]');
      const box = await stage.boundingBox();
      expect(box).toBeTruthy();

      // Click-to-position at ~25%.
      await page.mouse.click(box.x + box.width * 0.25, box.y + box.height * 0.5);
      await expect
        .poll(() => sliderValue(page), { message: "click positions the divider" })
        .toBeLessThanOrEqual(27);
      expect(await sliderValue(page)).toBeGreaterThanOrEqual(23);

      // Drag the handle to ~75% — same state authority (no second position).
      await page.mouse.move(box.x + box.width * 0.25, box.y + box.height * 0.5);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width * 0.75, box.y + box.height * 0.5, { steps: 8 });
      await page.mouse.up();
      const dragged = await sliderValue(page);
      expect(dragged).toBeGreaterThanOrEqual(73);
      expect(dragged).toBeLessThanOrEqual(77);

      // One authority: divider geometry equals aria-valuenow exactly.
      const authority = await page.evaluate(() => {
        const s = document.querySelector('[data-testid="cm-compare-slider"]');
        const d = document.querySelector(".cm-compare-divider");
        return { now: s.getAttribute("aria-valuenow"), left: d.style.left };
      });
      expect(authority.left).toBe(authority.now + "%");
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("E. replacement: a third eligible image replaces B; A unchanged; hint shown", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("history");
      await openGenerationDetail(page, "gen_multi");
      await page.locator('[data-testid="history-v2-compare"]').click();
      await expect(page.locator('[data-testid="cm-compare-tray-a"]')).toHaveText(/^A: Preview/);

      await addOutputToCompare(page, 0);
      await expect(page.locator('[data-testid="cm-compare-tray-b"]')).toHaveText(/^B: Output 1/);

      // The next eligible pick truthfully replaces B and says so up front.
      await page
        .locator(OVERLAY)
        .locator(".comfymodal-studio-history-v2-menu-btn")
        .nth(1)
        .click();
      const replaceItem = page.locator('[data-testid="history-v2-output-add-to-compare-1"]');
      await expect(replaceItem).toBeVisible();
      await expect(replaceItem.locator(".cm-compare-replace-hint")).toHaveText("Replaces B");
      await replaceItem.click();

      await expect(page.locator('[data-testid="cm-compare-tray-b"]')).toHaveText(/^B: Output 2/);
      await expect(page.locator('[data-testid="cm-compare-tray-a"]')).toHaveText(/^A: Preview/);

      await openCompareView(page);
      await expect(page.locator('[data-testid="cm-compare-title"]')).toHaveText(
        "Comparing Preview ↔ Output 2"
      );
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("F. Escape closes the view, clears the session, restores focus; History detail stays valid", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("history");
      await openGenerationDetail(page, "gen_ok");
      await page.locator('[data-testid="history-v2-compare"]').click();
      await addOutputToCompare(page, 0);
      await openCompareView(page);

      await page.keyboard.press("Escape");
      await expect(page.locator('[data-testid="cm-compare-overlay"]')).toHaveCount(0);
      // Session cleared: the tray is gone entirely.
      await expect(page.locator('[data-testid="cm-compare-tray"]')).toHaveCount(0);

      // Focus restored to the origin invoker (the detail Compare action,
      // re-resolved by its stable testid after the tray opener was removed).
      const focusFacts = await page.evaluate((sel) => {
        const ae = document.activeElement;
        const ov = document.querySelector(sel);
        return {
          testid: ae && ae.getAttribute ? ae.getAttribute("data-testid") : null,
          insideDetail: !!ov && ov.contains(ae),
        };
      }, OVERLAY);
      expect(focusFacts.testid).toBe("history-v2-compare");
      expect(focusFacts.insideDetail).toBe(true);

      // Underlying History detail remains fully functional afterwards.
      const overlay = page.locator(OVERLAY);
      await expect(overlay.locator(".comfymodal-studio-history-v2-run-line")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(overlay).toHaveCount(0);
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("G. responsive 768/480/360: no overflow, narrow stacked mode ≤640px, slider operable", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("history");
      await expect(
        page.locator('[data-testid="history-v2-generation-card"]').first()
      ).toBeVisible({ timeout: 15000 });

      const assetUrl = await page
        .locator("img.comfymodal-studio-history-v2-thumb-img")
        .first()
        .getAttribute("src");
      expect(assetUrl).toBeTruthy();

      for (const width of [768, 480, 360]) {
        await page.setViewportSize({ width, height: 900 });
        await page.evaluate(async ({ url }) => {
          const m = await import("/extensions/comfymodal-modal/studio-image-compare.js");
          m.startCompare({ descriptor: { url, label: "Preview", kind: "preview" } });
          m.addToCompareB({ descriptor: { url, label: "Original", kind: "original" } });
          m.openCompareView(null);
        }, { url: assetUrl });

        await expect(page.locator('[data-testid="cm-compare-overlay"]')).toBeVisible();
        const mode = await page
          .locator('[data-testid="cm-compare-stage"]')
          .getAttribute("data-mode");
        expect(mode, `mode at ${width}px`).toBe(width <= 640 ? "stacked" : "overlay");

        const overflow = await page.evaluate(() => ({
          scroll: document.documentElement.scrollWidth,
          client: document.documentElement.clientWidth,
        }));
        expect(overflow.scroll, `no horizontal overflow at ${width}px`).toBeLessThanOrEqual(
          overflow.client
        );

        // Labels remain visible; slider stays keyboard-operable.
        await expect(page.locator('[data-testid="cm-compare-label-a"]')).toBeVisible();
        await expect(page.locator('[data-testid="cm-compare-label-b"]')).toBeVisible();
        await page.locator('[data-testid="cm-compare-slider"]').focus();
        await page.keyboard.press("Home");
        expect(await sliderValue(page)).toBe(0);
        await page.keyboard.press("End");
        expect(await sliderValue(page)).toBe(100);

        await page.keyboard.press("Escape");
        await expect(page.locator('[data-testid="cm-compare-overlay"]')).toHaveCount(0);
        await expect(page.locator('[data-testid="cm-compare-tray"]')).toHaveCount(0);
      }
      await page.setViewportSize({ width: 1440, height: 900 });
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("H. network proof: compare causes ONLY normal image GETs — zero writes or new routes", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("history");
      await openGenerationDetail(page, "gen_ok");

      // Collector starts AFTER the detail fetch settled: every request from
      // here on is attributable to compare interaction alone.
      const requests = [];
      page.on("request", (r) =>
        requests.push({ method: r.method(), url: r.url() })
      );
      const urlOf = (r) => r.url;

      await page.locator('[data-testid="history-v2-compare"]').click();
      await addOutputToCompare(page, 0);
      await openCompareView(page);

      // Manipulate the divider both ways.
      const box = await page.locator('[data-testid="cm-compare-stage"]').boundingBox();
      await page.mouse.click(box.x + box.width * 0.3, box.y + box.height * 0.5);
      await page.locator('[data-testid="cm-compare-slider"]').focus();
      await page.keyboard.press("ArrowLeft");
      await page.keyboard.press("Home");
      await page.keyboard.press("End");

      await page.keyboard.press("Escape");
      await expect(page.locator('[data-testid="cm-compare-overlay"]')).toHaveCount(0);

      const writes = requests.filter((r) => r.method !== "GET");
      expect(writes, `non-GET requests during compare: ${JSON.stringify(writes)}`).toEqual([]);
      // Everything else must be a normal A/B asset image GET. The harness's
      // own test-control event poll (__comfymodal_test/events) runs
      // independently of compare and is excluded as pre-existing behavior.
      const nonAssets = requests.filter(
        (r) =>
          !urlOf(r).includes("/comfymodal/history-v2/assets/") &&
          !urlOf(r).includes("/__comfymodal_test/events")
      );
      expect(nonAssets, `unexpected requests: ${JSON.stringify(nonAssets)}`).toEqual([]);
      expect(requests.some((r) => urlOf(r).includes("/comparison/"))).toBe(false);
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("I. retirement guard: no Comparison Profiles/Runner, no old A/B module, no /comparison/run", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("history");
      await expect(
        page.locator('[data-testid="history-v2-generation-card"]').first()
      ).toBeVisible({ timeout: 15000 });

      const census = await page.evaluate(() => {
        const text = document.body.innerText;
        return {
          hasProfiles: text.includes("Comparison Profiles"),
          hasRunner: text.includes("Comparison Runner"),
          hasRunRoute: text.includes("/comparison/run"),
          retiredNodes: document.querySelectorAll(
            "[class*='comparison-profile'], [class*='comparison-runner'], [class*='ab-slider']"
          ).length,
        };
      });
      expect(census.hasProfiles).toBe(false);
      expect(census.hasRunner).toBe(false);
      expect(census.hasRunRoute).toBe(false);
      expect(census.retiredNodes).toBe(0);

      const probes = await page.evaluate(async () => {
        const retired = await import("/extensions/comfymodal-modal/testing-dashboard/ab-slider.js")
          .then(() => false)
          .catch(() => true);
        return { retired };
      });
      expect(probes.retired, "retired A/B slider module must not exist").toBe(true);
      t.assertNoConsoleErrors(["Failed to load resource.*404"]);
    } finally {
      t.guard.dispose();
    }
  });

  test("J. image failure state: broken URL renders truthful unavailable note; labels stay; no crash", async ({
    page,
  }) => {
    const t = await setupFakeTest(page);
    try {
      await t.gotoPage("history");
      await expect(
        page.locator('[data-testid="history-v2-generation-card"]').first()
      ).toBeVisible({ timeout: 15000 });
      const assetUrl = await page
        .locator("img.comfymodal-studio-history-v2-thumb-img")
        .first()
        .getAttribute("src");

      await page.evaluate(async ({ url }) => {
        const m = await import("/extensions/comfymodal-modal/studio-image-compare.js");
        m.startCompare({ descriptor: { url, label: "Preview", kind: "preview" } });
        // Slot B points at an unregistered asset id — the engine 404s it.
        // It is never silently substituted with another image.
        m.addToCompareB({
          descriptor: {
            url: "/comfymodal/history-v2/assets/i5_missing_asset_probe",
            label: "Original",
            kind: "original",
          },
        });
        m.openCompareView(null);
      }, { url: assetUrl });

      await expect(page.locator('[data-testid="cm-compare-overlay"]')).toBeVisible();
      await expect(page.locator('[data-testid="cm-compare-unavailable-b"]')).toHaveText(
        "Image unavailable"
      );
      // A/B labels remain visible; the overlay stays interactive.
      await expect(page.locator('[data-testid="cm-compare-label-a"]')).toBeVisible();
      await expect(page.locator('[data-testid="cm-compare-label-b"]')).toBeVisible();
      const slider = page.locator('[data-testid="cm-compare-slider"]');
      await slider.focus();
      await page.keyboard.press("Home");
      expect(await sliderValue(page)).toBe(0);

      await page.keyboard.press("Escape");
      await expect(page.locator('[data-testid="cm-compare-overlay"]')).toHaveCount(0);
      t.assertNoConsoleErrors(["Failed to load resource.*404"]);
    } finally {
      t.guard.dispose();
    }
  });
});
