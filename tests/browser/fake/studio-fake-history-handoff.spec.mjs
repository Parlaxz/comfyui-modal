// Phase 10 history-handoff compare surfaces (fake backend, bounded).
//
// Proves the visual History gallery picker + polished compare viewer
// against the real frontend. The picker was rebuilt from two <select>
// dropdowns into a visual gallery: Compare (compare-open) opens the
// gallery overlay (compare-picker, z-10100), real cards are clicked for
// A and B (history-picker-badge-a/b, history-picker-slot-a/b), Swap
// exchanges sides, same-asset A/B keeps Compare disabled, and
// compare-start opens the divider overlay with zoom toolbar, identity
// strip, and Swap/Change/Back controls.
//
// Selector sources (EVERY selector verified against current web/ before use):
//   web/studio-history-picker.js openHistoryPicker ("compare-picker",
//     "history-picker-grid/current/slot-a/slot-b/swap/search/filter-status/
//     filter-fav/sort/more/cancel", "compare-picker-close" alias,
//     "compare-start"/"history-picker-confirm", "history-picker-badge-a/b",
//     "history-picker-card")
//   web/studio-image-compare.js openComparePair/openCompareView +
//     _openViewerGallery ("cm-compare-overlay", "cm-compare-slider",
//     "cm-zoom-bar", "cm-zoom-fit/11/in/out/label", "cm-compare-close",
//     "compare-swap-view", "compare-change-a/b", "compare-back",
//     "compare-identity", "cm-compare-img-a/b")
//   web/studio-ui.js buildViewerHandoffButtons ("viewer-use-as-current",
//     "viewer-edit", "viewer-post-process", "viewer-upscale") and
//     buildViewerShell (".comfymodal-studio-viewer-overlay")
//   web/studio-history-v2.js openGeneration card wiring
//     ("history-v2-generation-card") + the four Phase 10 handoff handlers
//
// CORRECTIVE (compare-does-nothing): the picker opened at z-index 80,
// underneath the Studio overlay stack (viewer 10050, tray 10070, compare
// view 10080, queue viewer 10090), so the click visibly did nothing while
// the DOM insisted the picker was open. The picker now opens at 10100
// (pinned by T1), and openComparePair propagates the view result instead
// of reporting success when no view opened (pinned by T7).

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const TOPBAR = '[data-testid="workspace-topbar"]';
const RUN_BTN = '[data-testid="run-btn"]';
const PICKER = '[data-testid="compare-picker"]';
const GRID = '[data-testid="history-picker-grid"]';
const CARD = '[data-testid="history-picker-card"]';
const OVERLAY = '[data-testid="cm-compare-overlay"]';
const SLIDER = '[data-testid="cm-compare-slider"]';
const ZOOM_FIT = '[data-testid="cm-zoom-fit"]';
const ZOOM_11 = '[data-testid="cm-zoom-11"]';
const ZOOM_IN = '[data-testid="cm-zoom-in"]';
const ZOOM_OUT = '[data-testid="cm-zoom-out"]';
const ZOOM_LABEL = '[data-testid="cm-zoom-label"]';
const GEN_CARD = '[data-testid="history-v2-generation-card"]';
const THUMB_IMG = "img.comfymodal-studio-history-v2-thumb-img";
// Current shared viewer shell (web/studio-ui.js buildViewerShell).
const VIEWER_OVERLAY = ".comfymodal-studio-viewer-overlay";

// Pre-existing shell↔fake-server gap: web/studio-shell.js polls
// `${apiBase}/sync/status`, which the fake server does not implement. The
// console text carries no URL, so track 4xx URLs directly and assert
// sync/status is the only one; any other 4xx fails the test.
const ALLOW = [/Failed to load resource.*404/];
function watch4xx(page) {
  const bad = [];
  page.on("response", (r) => { if (r.status() >= 400) bad.push(r.status() + " " + r.url()); });
  return bad;
}
function expectOnlySync404(bad) {
  const other = bad.filter((u) => u.indexOf("sync/status") === -1);
  expect(other).toEqual([]);
}

// The gallery loads async (repository listFeed + 200ms search debounce).
// Wait until real History cards are rendered.
async function expectGalleryCards(page, min = 2) {
  const cards = page.locator(CARD);
  await expect.poll(async () => cards.count(), {
    timeout: 15000,
    message: `expected at least ${min} history gallery cards`,
  }).toBeGreaterThanOrEqual(min);
  return cards;
}

async function openGallery(page) {
  await expect(page.locator(TOPBAR)).toBeVisible({ timeout: 10000 });
  await page.locator('[data-testid="compare-open"]').click();
  const picker = page.locator(PICKER);
  await expect(picker).toBeVisible({ timeout: 10000 });
  return picker;
}

test.describe("History handoff compare surfaces (fake backend)", () => {
  test("T1 — topbar Compare launcher opens the visual history gallery", async ({
    page,
  }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await expect(page.locator(TOPBAR)).toBeVisible({ timeout: 10000 });
    await expect(page.locator(RUN_BTN)).toBeVisible({ timeout: 10000 });
    // The Compare launcher sits beside RUN and opens the gallery picker.
    const launcher = page.locator('[data-testid="compare-open"]');
    await expect(launcher).toBeVisible({ timeout: 10000 });
    await launcher.click();
    const picker = page.locator(PICKER);
    await expect(picker).toBeVisible({ timeout: 10000 });
    // Corrective pin: the picker must sit above the Studio overlay stack.
    await expect(picker).toHaveCSS("z-index", "10100");
    // Gallery chrome: grid, Current Canvas note OUTSIDE the grid when no
    // canvas image exists (no dead card), A/B slots, controls.
    await expect(page.locator(GRID)).toBeVisible({ timeout: 10000 });
    const current = page.locator('[data-testid="history-picker-current"]');
    await expect(current).toBeVisible({ timeout: 10000 });
    await expect(current).toContainText(/Current canvas/);
    await expect(page.locator(`${GRID} [data-testid="history-picker-current"]`)).toHaveCount(0);
    await expect(page.locator('[data-testid="history-picker-slot-a"]')).toBeVisible();
    await expect(page.locator('[data-testid="history-picker-slot-b"]')).toBeVisible();
    await expect(page.locator('[data-testid="history-picker-search"]')).toBeVisible();
    await expect(page.locator('[data-testid="history-picker-filter-status"]')).toBeVisible();
    await expect(page.locator('[data-testid="history-picker-sort"]')).toBeVisible();
    // Real History cards load from the fake backend, with a result count.
    const cards = await expectGalleryCards(page, 2);
    await expect(page.locator('[data-testid="history-picker-count"]')).toContainText(/\d+ (images|matches)/);
    // Mark A and B so the proof shot shows the badged multi-column grid.
    await cards.nth(0).click();
    await expect(page.locator('[data-testid="history-picker-badge-a"]')).toBeVisible({ timeout: 5000 });
    await cards.nth(1).click();
    await expect(page.locator('[data-testid="history-picker-badge-b"]')).toBeVisible({ timeout: 5000 });
    await page.screenshot({ path: "test-results/proof/phase10-history-grid-picker.png" });
    // Dismissal: Close button, Escape, backdrop click.
    await page.locator('[data-testid="compare-picker-close"]').click();
    await expect(picker).toHaveCount(0);
    await launcher.click();
    await expect(picker).toBeVisible({ timeout: 10000 });
    await page.keyboard.press("Escape");
    await expect(picker).toHaveCount(0);
    await launcher.click();
    await expect(picker).toBeVisible({ timeout: 10000 });
    await page.mouse.click(8, 8);
    await expect(picker).toHaveCount(0);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T2 — gallery pair flow: search, A/B picks, duplicate block, Swap, Compare", async ({
    page,
  }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    const picker = await openGallery(page);
    const cards = await expectGalleryCards(page, 3);
    const start = page.locator('[data-testid="compare-start"]');
    // Nothing picked yet: Compare stays disabled.
    await expect(start).toBeDisabled();
    // Status filter carries the explicit label.
    await expect(page.locator('[data-testid="history-picker-filter-status"]')).toContainText("All statuses");

    // Search narrows the grid: a nonsense token empties it, clearing
    // restores it.
    const search = page.locator('[data-testid="history-picker-search"]');
    const before = await cards.count();
    const firstText = (await cards.first().textContent()) || "";
    const token = (firstText.split(/\s+/).find((w) => w.length >= 4) || "").slice(0, 12);
    if (token) {
      await search.fill(token);
      await expect.poll(async () => page.locator(CARD).count(), {
        timeout: 10000,
        message: "search token did not filter the grid",
      }).toBeLessThanOrEqual(before);
      await expect.poll(async () => page.locator(CARD).count(), {
        timeout: 10000,
      }).toBeGreaterThanOrEqual(1);
      await page.screenshot({ path: "test-results/proof/phase10-history-grid-picker-search.png" });
    }
    await search.fill("zzz-no-such-history-zzz");
    await expect.poll(async () => page.locator(CARD).count(), { timeout: 10000 }).toBe(0);
    await search.fill("");
    await expect.poll(async () => page.locator(CARD).count(), {
      timeout: 10000,
      message: "clearing search did not restore the grid",
    }).toBeGreaterThanOrEqual(2);

    // Real pair picks: click two distinct cards.
    await page.locator(CARD).nth(0).click();
    const slotA = page.locator('[data-testid="history-picker-slot-a"]');
    const slotB = page.locator('[data-testid="history-picker-slot-b"]');
    await expect(page.locator('[data-testid="history-picker-badge-a"]')).toBeVisible({ timeout: 5000 });
    await expect(slotA).not.toContainText("Select A");
    await expect(start).toBeDisabled();
    await page.locator(CARD).nth(1).click();
    await expect(page.locator('[data-testid="history-picker-badge-b"]')).toBeVisible({ timeout: 5000 });
    await expect(slotB).not.toContainText("Select B");
    await expect(start).toBeEnabled({ timeout: 5000 });

    // Same-image picks are rejected with an explanation: re-arm B and
    // re-click the A card — the pair is preserved, Compare stays enabled,
    // and the inline message names the side that already holds it.
    // Mirror: re-arm A and re-click the B card.
    const dup = page.locator('[data-testid="history-picker-dup-message"]');
    const instruction = page.locator('[data-testid="history-picker-instruction"]');
    await slotB.click();
    await expect(instruction).toContainText("Choose a replacement for B");
    await expect(slotB).toHaveAttribute("aria-pressed", "true");
    await page.locator(CARD).nth(0).click();
    await expect(dup).toContainText("Already selected as A. Choose another image for B.");
    await expect(page.locator('[data-testid="history-picker-badge-a"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="history-picker-badge-b"]')).toHaveCount(1);
    await expect(start).toBeEnabled({ timeout: 5000 });
    await slotA.click();
    await expect(instruction).toContainText("Choose a replacement for A");
    await page.locator(CARD).nth(1).click();
    await expect(dup).toContainText("Already selected as B. Choose another image for A.");
    await expect(page.locator('[data-testid="history-picker-badge-a"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="history-picker-badge-b"]')).toHaveCount(1);
    await expect(start).toBeEnabled({ timeout: 5000 });

    // Swap exchanges the sides (the A/B prefix stays with the slot; the
    // image label moves).
    const aBefore = await slotA.textContent();
    const bBefore = await slotB.textContent();
    const aLabel = String(aBefore).replace(/^[AB] — /, "");
    const bLabel = String(bBefore).replace(/^[AB] — /, "");
    await page.locator('[data-testid="history-picker-swap"]').click();
    await expect.poll(async () => slotA.textContent(), { timeout: 5000 }).toBe("A — " + bLabel);
    await expect.poll(async () => slotB.textContent(), { timeout: 5000 }).toBe("B — " + aLabel);
    await expect(start).toBeEnabled();

    // Slots re-arm a side: arm A, pick the third card, A follows it.
    await slotA.click();
    const swappedA = await slotA.textContent();
    await page.locator(CARD).nth(2).click();
    await expect.poll(async () => slotA.textContent(), { timeout: 5000 }).not.toBe(swappedA);
    await expect(start).toBeEnabled({ timeout: 5000 });

    // Compare opens the divider overlay and closes the picker.
    await start.click();
    const overlay = page.locator(OVERLAY);
    await expect(overlay).toBeVisible({ timeout: 10000 });
    await expect(picker).toHaveCount(0);
    await expect(page.locator(SLIDER)).toBeVisible({ timeout: 10000 });
    for (const btn of [ZOOM_FIT, ZOOM_11, ZOOM_IN, ZOOM_OUT]) {
      await expect(page.locator(btn)).toBeVisible({ timeout: 10000 });
    }
    const label = page.locator(ZOOM_LABEL);
    await expect(label).toHaveText("100%");
    await page.locator(ZOOM_FIT).click();
    await expect(label).toHaveText("Fit");
    await page.locator(ZOOM_11).click();
    await expect(label).toHaveText("100%");
    // Polished viewer chrome: identity strip + Swap/Change/Back.
    await expect(page.locator('[data-testid="compare-identity"]')).toContainText("A —");
    await expect(page.locator('[data-testid="compare-identity"]')).toContainText("B —");
    await expect(page.locator('[data-testid="compare-swap-view"]')).toBeVisible();
    await expect(page.locator('[data-testid="compare-change-a"]')).toBeVisible();
    await expect(page.locator('[data-testid="compare-change-b"]')).toBeVisible();
    await expect(page.locator('[data-testid="compare-back"]')).toBeVisible();
    await page.screenshot({ path: "test-results/proof/phase10-compare-view-polished.png" });

    await page.locator('[data-testid="cm-compare-close"]').click();
    await expect(page.locator(OVERLAY)).toHaveCount(0);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T3 — two resolvable picks open the compare overlay; Fit / 1:1 labels", async ({
    page,
  }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await fx.gotoPage("history");
    await expect(page.locator(GEN_CARD).first()).toBeVisible({ timeout: 15000 });

    // Two DISTINCT real History thumb URLs: genuinely resolvable picks.
    const urls = await page
      .locator(THUMB_IMG)
      .evaluateAll((imgs) =>
        Array.from(new Set(imgs.map((i) => i.getAttribute("src")).filter(Boolean))).slice(0, 2)
      );
    expect(urls.length).toBe(2);

    const opened = await page.evaluate(async ([a, b]) => {
      const m = await import("/extensions/comfymodal-modal/studio-image-compare.js");
      return m.openComparePair({
        a: { url: a, label: "Pick A" },
        b: { url: b, label: "Pick B" },
      });
    }, urls);
    expect(opened).toBe(true);

    const overlay = page.locator(OVERLAY);
    await expect(overlay).toBeVisible({ timeout: 10000 });
    await expect(page.locator(SLIDER)).toBeVisible({ timeout: 10000 });
    for (const btn of [ZOOM_FIT, ZOOM_11, ZOOM_IN, ZOOM_OUT]) {
      await expect(page.locator(btn)).toBeVisible({ timeout: 10000 });
    }
    const label = page.locator(ZOOM_LABEL);
    await expect(label).toHaveText("100%");
    await page.locator(ZOOM_FIT).click();
    await expect(label).toHaveText("Fit");
    await page.locator(ZOOM_11).click();
    await expect(label).toHaveText("100%");

    await page.locator('[data-testid="cm-compare-close"]').click();
    await expect(page.locator(OVERLAY)).toHaveCount(0);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T4 — History viewer overlay renders all four handoff buttons", async ({
    page,
  }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    // The harness CAN open a real viewer overlay: History → gen_ok detail.
    // studio-history-v2.js passes all four Phase 10 handlers
    // (onUseAsCurrent/onEdit/onPostProcess/onUpscale) whenever navigation
    // exists, so buildViewerHandoffButtons renders one button each.
    await fx.gotoPage("history");
    const card = page.locator(`${GEN_CARD}[data-id="gen_ok"]`);
    await expect(card).toBeVisible({ timeout: 15000 });
    await card.click();
    const detail = page.locator(VIEWER_OVERLAY);
    await expect(detail).toBeVisible({ timeout: 10000 });
    await expect(detail.locator('[data-testid="viewer-use-as-current"]')).toContainText(
      "Use as Current"
    );
    await expect(detail.locator('[data-testid="viewer-edit"]')).toContainText("Edit");
    await expect(detail.locator('[data-testid="viewer-post-process"]')).toContainText(
      "Post Process"
    );
    await expect(detail.locator('[data-testid="viewer-upscale"]')).toContainText("Upscale");
    await page.keyboard.press("Escape");
    await expect(page.locator(VIEWER_OVERLAY)).toHaveCount(0);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  // T6 — viewer Change-A/Back round-trip through the real gallery, no
  // module import: Change A reopens the picker (selections preserved,
  // view still open underneath), picking a replacement refreshes the
  // open view in place; Back returns to the picker with selections.
  test("T6 — compare viewer Change-A replaces and Back returns to picker", async ({
    page,
  }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    const picker = await openGallery(page);
    const cards = await expectGalleryCards(page, 3);
    await cards.nth(0).click();
    await cards.nth(1).click();
    const start = page.locator('[data-testid="compare-start"]');
    await expect(start).toBeEnabled({ timeout: 5000 });
    await start.click();
    const overlay = page.locator(OVERLAY);
    await expect(overlay).toBeVisible({ timeout: 10000 });
    await expect(picker).toHaveCount(0);

    // Escape with the gallery above the view dismisses ONLY the gallery:
    // the compare view stays open underneath (layer-registry ordering).
    await page.locator('[data-testid="compare-change-a"]').click();
    const escGallery = page.locator(PICKER);
    await expect(escGallery).toBeVisible({ timeout: 10000 });
    await expect(overlay).toBeVisible({ timeout: 5000 });
    await page.keyboard.press("Escape");
    await expect(escGallery).toHaveCount(0);
    await expect(overlay).toBeVisible({ timeout: 5000 });

    // Change A: the gallery reopens above the still-open view, keeping
    // the live pair as its selections, armed at A.
    const imgA = page.locator('[data-testid="cm-compare-img-a"]');
    const imgB = page.locator('[data-testid="cm-compare-img-b"]');
    const srcBefore = await imgA.getAttribute("src");
    expect(srcBefore).toBeTruthy();
    await page.locator('[data-testid="compare-change-a"]').click();
    const gallery = page.locator(PICKER);
    await expect(gallery).toBeVisible({ timeout: 10000 });
    await expect(overlay).toBeVisible({ timeout: 5000 });
    await expect(page.locator('[data-testid="history-picker-slot-a"]')).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator('[data-testid="history-picker-instruction"]')).toContainText("Choose a replacement for A");
    await expect(page.locator('[data-testid="history-picker-badge-a"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="history-picker-badge-b"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="history-picker-slot-a"]')).not.toContainText("Select A");
    // Pick a replacement that is neither side: the open view updates.
    const galleryUrls = await page
      .locator(`${CARD}[data-gallery-url]`)
      .evaluateAll((els) => els.map((e) => e.getAttribute("data-gallery-url")));
    const bUrl = await page.locator('[data-testid="cm-compare-img-b"]').getAttribute("src");
    const replIdx = galleryUrls.findIndex((u) => u && u !== srcBefore && u !== bUrl);
    expect(replIdx).toBeGreaterThanOrEqual(0);
    await page.locator(CARD).nth(replIdx).click();
    await page.locator('[data-testid="compare-start"]').click();
    await expect.poll(async () => imgA.getAttribute("src"), {
      timeout: 10000,
      message: "Change-A replacement did not refresh the open view",
    }).not.toBe(srcBefore);
    await expect(overlay).toBeVisible({ timeout: 5000 });

    // Change B arms B: the next pick replaces B and leaves A untouched.
    // Switching the sort here also probes filter retention for Back.
    const srcAAfter = await imgA.getAttribute("src");
    const srcBBefore = await imgB.getAttribute("src");
    await page.locator('[data-testid="compare-change-b"]').click();
    const galleryB = page.locator(PICKER);
    await expect(galleryB).toBeVisible({ timeout: 10000 });
    await expect(overlay).toBeVisible({ timeout: 5000 });
    await expect(page.locator('[data-testid="history-picker-slot-b"]')).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator('[data-testid="history-picker-instruction"]')).toContainText("Choose a replacement for B");
    await page.locator('[data-testid="history-picker-sort"]').selectOption("oldest");
    await expect.poll(async () => page.locator(CARD).count(), {
      timeout: 10000,
      message: "sort change did not reload the gallery",
    }).toBeGreaterThanOrEqual(2);
    const galleryBUrls = await page
      .locator(`${CARD}[data-gallery-url]`)
      .evaluateAll((els) => els.map((e) => e.getAttribute("data-gallery-url")));
    const replBIdx = galleryBUrls.findIndex((u) => u && u !== srcAAfter && u !== srcBBefore);
    expect(replBIdx).toBeGreaterThanOrEqual(0);
    await page.locator(CARD).nth(replBIdx).click();
    await page.locator('[data-testid="compare-start"]').click();
    await expect.poll(async () => imgB.getAttribute("src"), {
      timeout: 10000,
      message: "Change-B replacement did not refresh the open view",
    }).not.toBe(srcBBefore);
    expect(await imgA.getAttribute("src")).toBe(srcAAfter);
    await expect(overlay).toBeVisible({ timeout: 5000 });

    // Back: the view closes and the gallery returns with selections and
    // the retained sort.
    await page.locator('[data-testid="compare-back"]').click();
    await expect(overlay).toHaveCount(0);
    const back = page.locator(PICKER);
    await expect(back).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="history-picker-sort"]')).toHaveValue("oldest");
    await expect(page.locator('[data-testid="history-picker-badge-a"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="history-picker-badge-b"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="history-picker-slot-a"]')).not.toContainText("Select A");
    await expect(page.locator('[data-testid="history-picker-slot-b"]')).not.toContainText("Select B");
    await page.locator('[data-testid="compare-picker-close"]').click();
    await expect(back).toHaveCount(0);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  // T7 — openComparePair must not report success when the view cannot open
  // (a view is already showing): otherwise the picker closes and the user
  // is stranded with no view and no error.
  test("T7 — openComparePair reports view-blocked instead of fake success", async ({
    page,
  }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await fx.gotoPage("history");
    await expect(page.locator(GEN_CARD).first()).toBeVisible({ timeout: 15000 });
    const urls = await page
      .locator(THUMB_IMG)
      .evaluateAll((imgs) =>
        Array.from(new Set(imgs.map((i) => i.getAttribute("src")).filter(Boolean))).slice(0, 2)
      );
    expect(urls.length).toBe(2);
    const [first, second] = await page.evaluate(async ([a, b]) => {
      const m = await import("/extensions/comfymodal-modal/studio-image-compare.js");
      const one = m.openComparePair({
        a: { url: a, label: "Pick A" },
        b: { url: b, label: "Pick B" },
      });
      const two = m.openComparePair({
        a: { url: b, label: "Pick B2" },
        b: { url: a, label: "Pick A2" },
      });
      return [one, two];
    }, urls);
    expect(first).toBe(true);
    expect(second).toBe(false);
    await expect(page.locator(OVERLAY)).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="cm-compare-close"]').click();
    await expect(page.locator(OVERLAY)).toHaveCount(0);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  // T5 — History pending-image state helpers (setPendingPlaygroundImage and
  // friends in web/studio-playground-state.js) are in-memory module state
  // consumed by the next Playground build: there is no DOM surface to drive
  // from a browser spec without mocking the viewer/page plumbing, so per the
  // brief this is intentionally NOT unit-tested here. Their observable
  // effects (canvas image + mode switch after clicking a handoff button)
  // belong to a future interaction spec, not this bounded handoff spec.
  test.skip("T5 — pending-image helpers are in-memory (no browser coverage)", async () => {});
});
