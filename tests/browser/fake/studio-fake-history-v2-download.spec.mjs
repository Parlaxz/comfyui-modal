// F3 Follow-Up A — Modern History V2 Browser Download deterministic coverage.
//
// Proves the mounted History V2 product's per-output Browser Download actions
// against the fake backend: Preview/Original variant separation, no-eager-
// Original fetch, multi-output addressing, truthful failure recovery,
// in-flight guarding, and ZERO export-state coupling.  Experiment cells get
// Generation-backed parity through their own detail pane.
//
// Fanout/counting authority: the PAGE's own network requests (one explicit
// click ⇒ exactly one managed-asset request).  The fake server's per-session
// asset counters back the no-eager-Original assertions.  Byte comparisons use
// independent API fetches of the SAME projected URLs.
//
// These tests do NOT cover configured-folder Export (a later F3 lane) and
// must never touch /run-history/{id}/save or any export route.

import { test, expect } from "@playwright/test";
import fs from "node:fs";
import { setupFakeTest } from "./helpers.mjs";

// ── Shared helpers ────────────────────────────────────────────────────────

function assetIdOf(url) {
  return String(url || "").split("/assets/")[1] || "";
}

/** Capture every ASSET request the PAGE initiates while installed. */
function trackAssetRequests(page) {
  const urls = [];
  const onReq = (r) => {
    if (r.url().includes("/history-v2/assets/")) urls.push(r.url());
  };
  page.on("request", onReq);
  return {
    urls,
    countFor(assetId) {
      return urls.filter((u) => assetIdOf(u) === assetId).length;
    },
    dispose() {
      page.off("request", onReq);
    },
  };
}

async function assetGetCount(fx, assetId) {
  const state = await fx.getState();
  return (state.assetGets && state.assetGets[assetId]) || 0;
}

async function fetchAssetBytes(page, fx, url) {
  const res = await page.request.get(
    `${url}?session=${encodeURIComponent(fx.sessionId)}`
  );
  expect(res.status()).toBe(200);
  return await res.body();
}

/** Trigger a download and capture suggested filename + bytes. */
async function captureDownload(page, trigger) {
  const dlPromise = page.waitForEvent("download");
  await trigger();
  const dl = await dlPromise;
  const path = await dl.path();
  return { name: dl.suggestedFilename(), bytes: fs.readFileSync(path) };
}

async function openGenerationDetail(page, id) {
  const card = page.locator(`.comfymodal-studio-history-v2-generation-card[data-id="${id}"]`);
  await expect(card).toBeVisible({ timeout: 15000 });
  await card.click();
  const overlay = page.locator('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]');
  await expect(overlay).toBeVisible({ timeout: 10000 });
  return overlay;
}

async function getDetailItem(page, fx, id) {
  const res = await page.request.get(
    `/comfymodal/history-v2/generations/${id}?session=${encodeURIComponent(fx.sessionId)}`
  );
  expect(res.status()).toBe(200);
  return (await res.json()).item;
}

/** Track any export/save-shaped request — browser download must never fire one. */
function trackExportRequests(page) {
  const hits = [];
  page.on("request", (r) => {
    if (/\/run-history\/[^/?]+\/save|\/exports(\?|$)|history-v2\/[^?]*\/export/.test(r.url())) {
      hits.push(r.url());
    }
  });
  return hits;
}

async function assertExportStateUntouched(fx, page, generationId) {
  const state = await fx.getState();
  expect(state.saveRequests).toEqual([]);
  if (generationId) {
    const item = await getDetailItem(page, fx, generationId);
    expect(item.export_state).toBe("none");
  }
}

async function seedAndOpenHistory(fx, scenario) {
  if (scenario) {
    const seeded = await fx.seedHistory(scenario);
    expect(seeded).toMatchObject({ status: "ok", v2: true });
    await fx.reload();
  }
  await fx.gotoPage("history");
}

// ── Single Generation matrix ─────────────────────────────────────────────

test.describe("F3 Browser Download — Single Generation (fake backend)", () => {

  test("1. preview-only output: Download Preview visible, Original absent, one fetch per click, .webp", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const assets = trackAssetRequests(page);
    try {
      await seedAndOpenHistory(fx);
      const overlay = await openGenerationDetail(page, "gen_preview_only");

      const previewBtn = overlay.locator('[data-testid="history-v2-download-preview"]');
      await expect(previewBtn).toHaveText("Download Preview");
      await expect(overlay.locator('[data-testid="history-v2-download-original"]')).toHaveCount(0);
      await expect(overlay.locator('[data-testid="history-v2-download-thumbnail"]')).toHaveCount(0);

      // One click ⇒ exactly one NEW managed-asset request for THIS variant
      // (the displayed preview image itself loads eagerly at render).
      const before = assets.countFor("gen_preview_only_o0_preview");
      const dl = await captureDownload(page, () => previewBtn.click());
      expect(dl.name).toBe("Landscape_Ultra_seed1000_out0_preview_gen_preview_only.webp");
      expect(assets.countFor("gen_preview_only_o0_preview")).toBe(before + 1);
      expect(dl.bytes).toEqual(await fetchAssetBytes(page, fx, "/comfymodal/history-v2/assets/gen_preview_only_o0_preview"));
      await expect(overlay.locator('[data-testid="history-v2-download-note"]')).toContainText("Downloaded");
      fx.assertNoConsoleErrors();
    } finally {
      assets.dispose();
      fx.guard.dispose();
    }
  });

  test("2. preview + original: distinct actions fetch only their own variant; export state untouched", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const assets = trackAssetRequests(page);
    try {
      await seedAndOpenHistory(fx);
      const hits = trackExportRequests(page);
      const overlay = await openGenerationDetail(page, "gen_ok");

      const previewBtn = overlay.locator('[data-testid="history-v2-download-preview"]');
      const originalBtn = overlay.locator('[data-testid="history-v2-download-original"]');
      await expect(previewBtn).toHaveText("Download Preview");
      await expect(originalBtn).toHaveText("Download Original");
      // View Original remains a separate display action.
      await expect(overlay.locator('[data-testid="history-v2-view-original"]')).toHaveText("View Original");
      // No-eager-Original: rendering never fetched the Original asset.
      expect(await assetGetCount(fx, "gen_ok_o0_orig")).toBe(0);

      const pdl = await captureDownload(page, () => previewBtn.click());
      expect(pdl.name).toBe("Portrait_Pro_seed1000_out0_preview_gen_ok.webp");
      expect(assets.countFor("gen_ok_o0_orig")).toBe(0);
      expect(pdl.bytes).toEqual(await fetchAssetBytes(page, fx, "/comfymodal/history-v2/assets/gen_ok_o0_preview"));

      const odl = await captureDownload(page, () => originalBtn.click());
      expect(odl.name).toBe("Portrait_Pro_seed1000_out0_original_gen_ok.png");
      // The Original click fetched the ORIGINAL only — never the Preview.
      expect(assets.countFor("gen_ok_o0_orig")).toBe(1);
      expect(odl.bytes).toEqual(await fetchAssetBytes(page, fx, "/comfymodal/history-v2/assets/gen_ok_o0_orig"));

      await assertExportStateUntouched(fx, page, "gen_ok");
      expect(hits).toEqual([]);
      fx.assertNoConsoleErrors();
    } finally {
      assets.dispose();
      fx.guard.dispose();
    }
  });

  test("3. original-only record: Download Original without View Original, zero pre-click GETs, .png", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const assets = trackAssetRequests(page);
    try {
      await seedAndOpenHistory(fx, "history_v2_phase_e");
      const overlay = await openGenerationDetail(page, "gen_phase_e_remote_original");

      const originalBtn = overlay.locator('[data-testid="history-v2-download-original"]');
      await expect(originalBtn).toHaveText("Download Original");
      await expect(overlay.locator('[data-testid="history-v2-download-preview"]')).toHaveCount(0);
      // The click itself is the explicit authorization — nothing fetched before it.
      expect(await assetGetCount(fx, "gen_phase_e_remote_original_o0_orig")).toBe(0);

      const dl = await captureDownload(page, () => originalBtn.click());
      expect(dl.name).toBe("Portrait_Pro_seed1000_out0_original_gen_phase_e_remote_original.png");
      expect(assets.countFor("gen_phase_e_remote_original_o0_orig")).toBe(1);
      expect(dl.bytes).toEqual(await fetchAssetBytes(page, fx, "/comfymodal/history-v2/assets/gen_phase_e_remote_original_o0_orig"));
      fx.assertNoConsoleErrors();
    } finally {
      assets.dispose();
      fx.guard.dispose();
    }
  });

  test("4. failed Original with retained Preview: no dead Original download, Preview still downloads, Retry kept", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const assets = trackAssetRequests(page);
    try {
      // gen_orig_failed_original: Preview retained, NO usable Original asset
      // (originalFailed, empty original projection) — the canonical
      // failed-Original record with an explicit Retry Original action.
      await seedAndOpenHistory(fx, "history_v2_phase_e_original");
      const overlay = await openGenerationDetail(page, "gen_orig_failed_original");

      await expect(overlay.locator('[data-testid="history-v2-download-original"]')).toHaveCount(0);
      await expect(overlay.locator('[data-testid="history-v2-retry-original"]')).toBeVisible();

      const previewBtn = overlay.locator('[data-testid="history-v2-download-preview"]');
      const dl = await captureDownload(page, () => previewBtn.click());
      expect(dl.name).toBe("Portrait_Pro_seed1000_out0_preview_gen_orig_failed_original.webp");
      expect(dl.bytes).toEqual(await fetchAssetBytes(page, fx, "/comfymodal/history-v2/assets/gen_orig_failed_original_o0_preview"));
      fx.assertNoConsoleErrors();
    } finally {
      assets.dispose();
      fx.guard.dispose();
    }
  });

  test("5. retained prior Original after failed rerender: Download Original targets the retained winner", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const assets = trackAssetRequests(page);
    try {
      await seedAndOpenHistory(fx, "history_v2_phase_e");
      const item = await getDetailItem(page, fx, "gen_phase_e_rerender_failed");
      const retainedUrl = item.outputs[0].original_url;
      expect(assetIdOf(retainedUrl)).toBe("gen_phase_e_rerender_failed_o0_orig");

      const overlay = await openGenerationDetail(page, "gen_phase_e_rerender_failed");
      const originalBtn = overlay.locator('[data-testid="history-v2-download-original"]');
      await expect(originalBtn).toHaveText("Download Original");
      expect(await assetGetCount(fx, "gen_phase_e_rerender_failed_o0_orig")).toBe(0);

      const dl = await captureDownload(page, () => originalBtn.click());
      expect(dl.name).toBe("Portrait_Pro_seed1000_out0_original_gen_phase_e_rerender_failed.png");
      // Exactly one request, aimed at the RETAINED winner URL.
      expect(assets.countFor("gen_phase_e_rerender_failed_o0_orig")).toBe(1);
      expect(assets.urls.filter((u) => assetIdOf(u) === "gen_phase_e_rerender_failed_o0_orig")[0])
        .toContain(retainedUrl);
      expect(dl.bytes).toEqual(await fetchAssetBytes(page, fx, retainedUrl));
      fx.assertNoConsoleErrors();
    } finally {
      assets.dispose();
      fx.guard.dispose();
    }
  });

  test("6. two logical outputs: each downloads its own bytes; featured state does not redirect", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedAndOpenHistory(fx);
      const item = await getDetailItem(page, fx, "gen_multi");
      const out1Url = item.outputs[0].original_url;
      const out2Url = item.outputs[1].original_url;
      const out1Bytes = await fetchAssetBytes(page, fx, out1Url);
      const out2Bytes = await fetchAssetBytes(page, fx, out2Url);
      expect(out1Bytes.equals(out2Bytes)).toBe(false);

      const overlay = await openGenerationDetail(page, "gen_multi");

      // Output 2 via its own actions menu.
      await overlay.getByRole("button", { name: "Output 2 actions" }).click();
      const dl2 = await captureDownload(page, () =>
        page.locator('[data-testid="history-v2-output-download-original-1"]').click()
      );
      expect(dl2.name).toBe("Portrait_Pro_seed1000_out1_original_gen_multi.png");
      expect(dl2.bytes.equals(out2Bytes)).toBe(true);
      expect(dl2.bytes.equals(out1Bytes)).toBe(false);

      // Feature output 3, then re-download output 2: identity unchanged.
      await overlay.getByRole("button", { name: "Output 3 actions" }).click();
      await page.getByRole("button", { name: "Set as featured" }).click();
      await expect(overlay.locator(".comfymodal-studio-history-v2-output-thumb").nth(2)).toHaveClass(
        /featured/, { timeout: 10000 }
      );
      await overlay.getByRole("button", { name: "Output 2 actions" }).click();
      const dl2b = await captureDownload(page, () =>
        page.locator('[data-testid="history-v2-output-download-original-1"]').click()
      );
      expect(dl2b.bytes.equals(out2Bytes)).toBe(true);
      expect(dl2b.bytes.equals(out1Bytes)).toBe(false);

      await assertExportStateUntouched(fx, page, "gen_multi");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("7. failed asset GET: truthful bounded failure, button recovers, retry succeeds, export state untouched", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const assets = trackAssetRequests(page);
    try {
      await seedAndOpenHistory(fx);
      const hits = trackExportRequests(page);
      const arm = await page.request.post("/__comfymodal_test/asset-fail", {
        data: { sessionId: fx.sessionId, assetId: "gen_ok_o0_orig", times: 1, status: 502 },
      });
      expect(arm.status()).toBe(200);

      const overlay = await openGenerationDetail(page, "gen_ok");
      const originalBtn = overlay.locator('[data-testid="history-v2-download-original"]');
      const note = overlay.locator('[data-testid="history-v2-download-note"]');

      await originalBtn.click();
      await expect(note).toHaveText("Download failed: HTTP 502");
      await expect(originalBtn).toBeEnabled();
      await expect(originalBtn).toHaveText("Download Original");
      expect(assets.countFor("gen_ok_o0_orig")).toBe(1);

      // Later retry succeeds; managed History record unchanged throughout.
      const dl = await captureDownload(page, () => originalBtn.click());
      expect(dl.name).toBe("Portrait_Pro_seed1000_out0_original_gen_ok.png");
      await expect(note).toContainText("Downloaded Portrait_Pro_seed1000_out0_original_gen_ok.png");
      expect(assets.countFor("gen_ok_o0_orig")).toBe(2);

      await assertExportStateUntouched(fx, page, "gen_ok");
      expect(hits).toEqual([]);
      fx.assertNoConsoleErrors(["Failed to load resource"]);
    } finally {
      assets.dispose();
      fx.guard.dispose();
    }
  });

  test("8. rapid double click while in flight: exactly one asset request", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const assets = trackAssetRequests(page);
    try {
      await seedAndOpenHistory(fx);
      await page.route("**/history-v2/assets/gen_ok_o0_orig*", async (route) => {
        await new Promise((r) => setTimeout(r, 400));
        await route.continue();
      });

      const overlay = await openGenerationDetail(page, "gen_ok");
      const originalBtn = overlay.locator('[data-testid="history-v2-download-original"]');
      await expect(originalBtn).toHaveText("Download Original");

      const dlPromise = page.waitForEvent("download");
      await originalBtn.click();
      await originalBtn.dispatchEvent("click"); // rapid second click mid-flight
      await dlPromise;
      expect(assets.countFor("gen_ok_o0_orig")).toBe(1);
      fx.assertNoConsoleErrors();
    } finally {
      assets.dispose();
      fx.guard.dispose();
    }
  });
});

// ── Experiment cell parity ───────────────────────────────────────────────

test.describe("F3 Browser Download — Experiment cells (fake backend)", () => {

  test("9. cell pane parity: per-cell Preview/Original downloads address their own Generation outputs", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const assets = trackAssetRequests(page);
    try {
      await seedAndOpenHistory(fx);
      const card = page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_completed"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      await card.click();
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 10000 });

      const cells = page.locator('[data-testid="history-v2-experiment-cell"]');
      await expect(cells).toHaveCount(4);

      // Select cell 0 (keyboard activation — grid tiles are role=button).
      await cells.nth(0).focus();
      await page.keyboard.press("Enter");
      const pane = page.locator('[data-testid="history-v2-cell-detail"]');
      await expect(pane).toBeVisible();
      const c0PreviewBtn = pane.locator('[data-testid="history-v2-cell-download-preview-exp_completed_cell_0"]');
      const c0OriginalBtn = pane.locator('[data-testid="history-v2-cell-download-original-exp_completed_cell_0"]');
      await expect(c0PreviewBtn).toHaveText("Download Preview");
      await expect(c0OriginalBtn).toHaveText("Download Original");
      // No-eager-Original at the experiment surface too.
      expect(await assetGetCount(fx, "exp_completed_c0_orig")).toBe(0);

      const c0dl = await captureDownload(page, () => c0PreviewBtn.click());
      expect(c0dl.name).toBe("Portrait_Pro_out0_preview.webp");
      expect(assets.countFor("exp_completed_c0_preview")).toBe(1);
      expect(c0dl.bytes).toEqual(await fetchAssetBytes(page, fx, "/comfymodal/history-v2/assets/exp_completed_c0_preview"));

      const c0odl = await captureDownload(page, () => c0OriginalBtn.click());
      expect(c0odl.name).toBe("Portrait_Pro_out0_original.png");
      expect(assets.countFor("exp_completed_c0_orig")).toBe(1);
      expect(c0odl.bytes).toEqual(await fetchAssetBytes(page, fx, "/comfymodal/history-v2/assets/exp_completed_c0_orig"));

      // Distinct cell identities cannot cross-download: cell 1 fetches ITS bytes.
      await cells.nth(1).focus();
      await page.keyboard.press("Enter");
      const c1PreviewBtn = pane.locator('[data-testid="history-v2-cell-download-preview-exp_completed_cell_1"]');
      const c1dl = await captureDownload(page, () => c1PreviewBtn.click());
      expect(assets.countFor("exp_completed_c1_preview")).toBe(1);
      expect(c1dl.bytes).toEqual(await fetchAssetBytes(page, fx, "/comfymodal/history-v2/assets/exp_completed_c1_preview"));
      expect(c1dl.bytes.equals(c0dl.bytes)).toBe(false);

      await assertExportStateUntouched(fx, page, null);
      fx.assertNoConsoleErrors();
    } finally {
      assets.dispose();
      fx.guard.dispose();
    }
  });

  test("10. Generate Original stays separate from Download; F2A cell favorite durable; experiment favorite independent", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedAndOpenHistory(fx, "history_v2_phase_e_original");
      const card = page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_phase_e_original"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      await card.click();
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 10000 });

      const cells = page.locator('[data-testid="history-v2-experiment-cell"]');
      await cells.nth(0).focus();
      await page.keyboard.press("Enter");
      const pane = page.locator('[data-testid="history-v2-cell-detail"]');
      await expect(pane).toBeVisible();

      // Preview-only cell: Download Preview present, Download Original absent,
      // Generate Original untouched beside it.
      const previewBtn = pane.locator('[data-testid="history-v2-cell-download-preview-exp_phase_e_original_cell_0"]');
      await expect(previewBtn).toHaveText("Download Preview");
      await expect(pane.locator('[data-testid^="history-v2-cell-download-original-"]')).toHaveCount(0);
      const genBtn = pane.locator('[data-testid="history-v2-cell-detail-generate-original-exp_phase_e_original_cell_0"]');
      await expect(genBtn).toHaveText("Generate Original");

      // Downloading Preview must NOT trigger an Original generation POST.
      const originalPosts = [];
      page.on("request", (r) => {
        if (/\/original/.test(r.url()) && r.method() === "POST") originalPosts.push(r.url());
      });
      const dl = await captureDownload(page, () => previewBtn.click());
      expect(dl.name).toBe("Portrait_Pro_out0_preview_gen_phase_e_original_cell_0.webp");
      expect(originalPosts).toEqual([]);
      await expect(genBtn).toHaveText("Generate Original");

      // F2A regression: the cell favorite drives its Generation durably while
      // the whole-Experiment favorite stays independent (and untouched by
      // downloads).
      const star = pane.locator('[data-testid="history-v2-cell-favorite"]');
      await expect(star).toHaveAttribute("aria-pressed", "false");
      await star.click();
      await expect(star).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      const state = await fx.getState();
      const gen = state.historyV2.find((r) => r.id === "gen_phase_e_original_cell_0");
      expect(gen.favorite).toBe(true);
      const exp = state.historyV2.find((r) => r.id === "exp_phase_e_original");
      expect(exp.favorite).toBe(false);

      await assertExportStateUntouched(fx, page, null);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("11. F1B regression: Cancel eligibility and cell menu behavior unchanged alongside downloads", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedAndOpenHistory(fx);
      const card = page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_running_1"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      await card.click();
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 10000 });

      // Durable Cancel eligibility (queued/running cells exist).
      const cancelBtn = page.locator('[data-testid="history-v2-experiment-cancel"]');
      await expect(cancelBtn).toBeVisible();
      await expect(cancelBtn).toHaveText("Cancel experiment");

      // Cell menu opens with zero error and closes without any cancel
      // request.  (This record's only menu item is disabled — unfocusable —
      // so the deterministic close path here is the outside-mousedown
      // handler; the keyboard Escape path is covered by the F1B suite on
      // enabled menus.)
      const menuBtn = page.locator('[data-testid="history-v2-experiment-cell"]').first()
        .locator(".comfymodal-studio-history-v2-menu-btn");
      await menuBtn.click();
      const menuItem = page.locator('[data-testid="history-v2-cell-generate-original"]');
      await expect(menuItem).toBeVisible();
      await page.mouse.click(10, 10);
      await expect(menuItem).toHaveCount(0);
      const state = await fx.getState();
      expect(state.saveRequests).toEqual([]);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
