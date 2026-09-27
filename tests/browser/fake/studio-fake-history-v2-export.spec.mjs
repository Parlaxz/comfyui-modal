// F10 — History V2 Configured-Folder Export deterministic coverage.
//
// Proves the mounted History V2 product's configured-folder Export actions
// against the frozen F9 fake contract: per-variant Preview/Original states
// (not_exported / exported / missing / failed), truthful retry + duplicate
// suppression, already_exported idempotency, partial failure truth,
// multi-output Asset identity, rerender successor semantics, Experiment cell
// parity, and the hard Download-vs-Export distinction — plus the F5
// favoriteOnly fake-parity closure (§F5.3).
//
// Fanout/counting authority: the PAGE's own network requests (one explicit
// click ⇒ exactly one bodyless export POST).  The fake rejects any export
// request carrying a body (400), so every successful UI export also proves
// bodylessness end-to-end.

import { test, expect } from "@playwright/test";
import fs from "node:fs";
import { setupFakeTest } from "./helpers.mjs";

// ── Shared helpers ────────────────────────────────────────────────────────

function assetIdOf(url) {
  return String(url || "").split("/assets/")[1]?.split("/")[0] || "";
}

/** Track every configured-export POST the PAGE initiates while installed. */
function trackExportPosts(page) {
  const hits = [];
  const onReq = (r) => {
    if (r.method() === "POST" && /\/history-v2\/assets\/[^/?]+\/export/.test(r.url())) {
      hits.push({ url: r.url(), postData: r.postData() });
    }
  };
  page.on("request", onReq);
  return {
    hits,
    urls() {
      return hits.map((h) => h.url);
    },
    dispose() {
      page.off("request", onReq);
    },
  };
}

async function exportPostCount(fx) {
  const state = await fx.getState();
  return (state.exportRequests || []).length;
}

async function exportRecordOf(fx, assetId) {
  const state = await fx.getState();
  return (state.exportRecords || {})[assetId] || null;
}

async function fetchAssetBytes(page, fx, url) {
  const res = await page.request.get(`${url}?session=${encodeURIComponent(fx.sessionId)}`);
  expect(res.status()).toBe(200);
  return await res.body();
}

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

async function apiExport(page, fx, assetId) {
  const res = await page.request.post(
    `/comfymodal/history-v2/assets/${assetId}/export?session=${encodeURIComponent(fx.sessionId)}`
  );
  expect(res.status()).toBe(200);
  return await res.json();
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

test.describe("F10 Configured Export — Single Generation (fake backend)", () => {

  test("1. Preview not_exported → Export Preview: one BODYLESS POST, durable exported suppression, Original independent", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackExportPosts(page);
    try {
      await seedAndOpenHistory(fx);
      const overlay = await openGenerationDetail(page, "gen_ok");

      const previewBtn = overlay.locator('[data-testid="history-v2-export-preview"]');
      const originalBtn = overlay.locator('[data-testid="history-v2-export-original"]');
      await expect(previewBtn).toHaveText("Export Preview");
      await expect(previewBtn).toBeEnabled();
      await expect(originalBtn).toHaveText("Export Original");

      // Capture the wire truth of the click (bodylessness cannot be faked:
      // the fake backend 400s any export request carrying a body).
      let wirePostData = "sentinel";
      await page.route("**/history-v2/assets/gen_ok_o0_preview/export", async (route) => {
        wirePostData = route.request().postData();
        await route.continue();
      });

      await previewBtn.click();
      await expect(overlay.locator('[data-testid="history-v2-export-note"]')).toContainText("Exported to");
      // Exactly ONE POST for THIS asset, bodyless on the wire.
      expect(posts.urls().filter((u) => u.includes("gen_ok_o0_preview")).length).toBe(1);
      expect(wirePostData).toBe(null);

      // Durable refetch is authoritative: projection flipped, redundant
      // action suppressed, and the ORIGINAL variant stays independently
      // not_exported (never collapsed to a generation-level "Exported").
      await expect(previewBtn).toHaveText("Preview exported", { timeout: 10000 });
      await expect(previewBtn).toBeDisabled();
      await expect(originalBtn).toHaveText("Export Original");
      await expect(originalBtn).toBeEnabled();
      const item = await getDetailItem(page, fx, "gen_ok");
      expect(item.outputs[0].preview_export_state).toBe("exported");
      expect(item.outputs[0].original_export_state).toBe("not_exported");
      expect((await exportRecordOf(fx, "gen_ok_o0_preview")).state).toBe("exported");
      fx.assertNoConsoleErrors();
    } finally {
      posts.dispose();
      fx.guard.dispose();
    }
  });

  test("2. Original independent export → both variants exported independently", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackExportPosts(page);
    try {
      await seedAndOpenHistory(fx);
      const overlay = await openGenerationDetail(page, "gen_ok");
      const previewBtn = overlay.locator('[data-testid="history-v2-export-preview"]');
      const originalBtn = overlay.locator('[data-testid="history-v2-export-original"]');

      await originalBtn.click();
      await expect(originalBtn).toHaveText("Original exported", { timeout: 10000 });
      await expect(originalBtn).toBeDisabled();
      // Preview untouched by the Original export.
      await expect(previewBtn).toHaveText("Export Preview");
      await expect(previewBtn).toBeEnabled();

      await previewBtn.click();
      await expect(previewBtn).toHaveText("Preview exported", { timeout: 10000 });
      const item = await getDetailItem(page, fx, "gen_ok");
      expect(item.outputs[0].preview_export_state).toBe("exported");
      expect(item.outputs[0].original_export_state).toBe("exported");
      expect(posts.hits.length).toBe(2);
      fx.assertNoConsoleErrors();
    } finally {
      posts.dispose();
      fx.guard.dispose();
    }
  });

  test("3. already_exported idempotent response: success, never failure (stale browser state)", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackExportPosts(page);
    try {
      await seedAndOpenHistory(fx);
      // Open the detail BEFORE the server-side export so the UI is stale.
      const overlay = await openGenerationDetail(page, "gen_preview_only");
      const previewBtn = overlay.locator('[data-testid="history-v2-export-preview"]');
      await expect(previewBtn).toHaveText("Export Preview");

      const api = await apiExport(page, fx, "gen_preview_only_o0_preview");
      expect(api.already_exported).toBe(false);

      await previewBtn.click();
      await expect(overlay.locator('[data-testid="history-v2-export-note"]')).toContainText("Already exported", { timeout: 10000 });
      await expect(previewBtn).toHaveText("Preview exported", { timeout: 10000 });
      expect(posts.hits.length).toBe(1);
      fx.assertNoConsoleErrors();
    } finally {
      posts.dispose();
      fx.guard.dispose();
    }
  });

  test("4. missing → 'Export Preview again' → exported; managed asset available throughout", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackExportPosts(page);
    try {
      await seedAndOpenHistory(fx);
      expect((await apiExport(page, fx, "gen_ok_o0_preview")).saved).toBe(true);
      const del = await page.request.post("/__comfymodal_test/export-delete", {
        data: { sessionId: fx.sessionId, assetId: "gen_ok_o0_preview" },
      });
      expect(del.status()).toBe(200);

      // Managed asset itself remains fully servable after external deletion.
      await fetchAssetBytes(page, fx, "/comfymodal/history-v2/assets/gen_ok_o0_preview");

      const overlay = await openGenerationDetail(page, "gen_ok");
      const previewBtn = overlay.locator('[data-testid="history-v2-export-preview"]');
      // Truthful missing state — never rendered as "never exported".
      await expect(previewBtn).toHaveText("Export Preview again");
      await expect(previewBtn).toBeEnabled();

      await previewBtn.click();
      await expect(overlay.locator('[data-testid="history-v2-export-note"]')).toContainText("Exported to", { timeout: 10000 });
      await expect(previewBtn).toHaveText("Preview exported", { timeout: 10000 });
      const item = await getDetailItem(page, fx, "gen_ok");
      expect(item.outputs[0].preview_export_state).toBe("exported");
      expect(posts.urls().filter((u) => u.includes("gen_ok_o0_preview")).length).toBe(1);
      fx.assertNoConsoleErrors();
    } finally {
      posts.dispose();
      fx.guard.dispose();
    }
  });

  test("5. failed → truthful bounded message → 'Retry export Preview' → exported", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackExportPosts(page);
    try {
      await seedAndOpenHistory(fx);
      const arm = await page.request.post("/__comfymodal_test/export-fail", {
        data: {
          sessionId: fx.sessionId,
          assetId: "gen_ok_o0_preview",
          times: 1,
          reason: "source_unreadable",
          message: "remote source unavailable",
        },
      });
      expect(arm.status()).toBe(200);

      const overlay = await openGenerationDetail(page, "gen_ok");
      const previewBtn = overlay.locator('[data-testid="history-v2-export-preview"]');
      const note = overlay.locator('[data-testid="history-v2-export-note"]');

      await previewBtn.click();
      // Backend message preferred, bounded, and NEVER generation-failure wording.
      await expect(note).toHaveText("Export failed: remote source unavailable", { timeout: 10000 });
      await expect(previewBtn).toHaveText("Retry export Preview", { timeout: 10000 });
      await expect(previewBtn).toBeEnabled();
      expect((await exportRecordOf(fx, "gen_ok_o0_preview")).state).toBe("failed");

      // Retry (arming consumed) succeeds and suppresses redundantly.
      await previewBtn.click();
      await expect(note).toContainText("Exported to", { timeout: 10000 });
      await expect(previewBtn).toHaveText("Preview exported", { timeout: 10000 });
      expect(posts.urls().filter((u) => u.includes("gen_ok_o0_preview")).length).toBe(2);
      fx.assertNoConsoleErrors(["Failed to load resource"]);
    } finally {
      posts.dispose();
      fx.guard.dispose();
    }
  });

  test("6. partial:true → distinct truthful failure, never shown as Exported", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackExportPosts(page);
    try {
      await seedAndOpenHistory(fx);
      const arm = await page.request.post("/__comfymodal_test/export-fail", {
        data: {
          sessionId: fx.sessionId,
          assetId: "gen_ok_o0_orig",
          times: 1,
          reason: "record_persist_failed",
          message: "copy written but not recorded",
          partial: true,
        },
      });
      expect(arm.status()).toBe(200);

      const overlay = await openGenerationDetail(page, "gen_ok");
      const originalBtn = overlay.locator('[data-testid="history-v2-export-original"]');
      const note = overlay.locator('[data-testid="history-v2-export-note"]');

      await originalBtn.click();
      await expect(note).toContainText("partially failed", { timeout: 10000 });
      await expect(note).toContainText("copy written but not recorded");
      await expect(note).not.toContainText("Exported to");
      // Durable refetch stays authoritative: failed, retry offered.
      await expect(originalBtn).toHaveText("Retry export Original", { timeout: 10000 });
      const item = await getDetailItem(page, fx, "gen_ok");
      expect(item.outputs[0].original_export_state).toBe("failed");
      fx.assertNoConsoleErrors(["Failed to load resource"]);
    } finally {
      posts.dispose();
      fx.guard.dispose();
    }
  });

  test("7a. preview-only record: Export Preview present, Export Original absent", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedAndOpenHistory(fx);
      const overlay = await openGenerationDetail(page, "gen_preview_only");
      await expect(overlay.locator('[data-testid="history-v2-export-preview"]')).toHaveText("Export Preview");
      await expect(overlay.locator('[data-testid="history-v2-export-original"]')).toHaveCount(0);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("7b. no-image record renders neither Export action", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedAndOpenHistory(fx);
      const overlay = await openGenerationDetail(page, "gen_no_image");
      await expect(overlay.locator('[data-testid="history-v2-export-preview"]')).toHaveCount(0);
      await expect(overlay.locator('[data-testid="history-v2-export-original"]')).toHaveCount(0);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("7c. failed Original with NO retained winner: no Export Original, Retry Original kept", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      // gen_orig_failed_original: Preview retained, explicit failed
      // Original-mode Attempt, NO usable Original asset projected.
      await seedAndOpenHistory(fx, "history_v2_phase_e_original");
      const item = await getDetailItem(page, fx, "gen_orig_failed_original");
      expect(item.outputs[0].original_asset_id).toBe(null);

      const overlay = await openGenerationDetail(page, "gen_orig_failed_original");
      await expect(overlay.locator('[data-testid="history-v2-export-preview"]')).toBeVisible();
      await expect(overlay.locator('[data-testid="history-v2-export-original"]')).toHaveCount(0);
      // The execution action survives independently of Export.
      await expect(overlay.locator('[data-testid="history-v2-retry-original"]')).toBeVisible();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("8. retained winner after failed rerender: Export Original targets the winner's Asset ID", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackExportPosts(page);
    try {
      await seedAndOpenHistory(fx, "history_v2_phase_e");
      const item = await getDetailItem(page, fx, "gen_phase_e_rerender_failed");
      expect(item.outputs[0].original_asset_id).toBe("gen_phase_e_rerender_failed_o0_orig");

      const overlay = await openGenerationDetail(page, "gen_phase_e_rerender_failed");
      const originalBtn = overlay.locator('[data-testid="history-v2-export-original"]');
      await expect(originalBtn).toHaveText("Export Original");
      await originalBtn.click();
      await expect(originalBtn).toHaveText("Original exported", { timeout: 10000 });
      expect(posts.urls().filter((u) => assetIdOf(u) === "gen_phase_e_rerender_failed_o0_orig").length).toBe(1);
      fx.assertNoConsoleErrors();
    } finally {
      posts.dispose();
      fx.guard.dispose();
    }
  });

  test("9. two logical outputs address different Assets; featured change never redirects Export", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackExportPosts(page);
    try {
      await seedAndOpenHistory(fx);
      const overlay = await openGenerationDetail(page, "gen_multi");

      // Output 2 via its own ⋮ menu: exports ITS OWN Preview Asset.
      await overlay.getByRole("button", { name: "Output 2 actions" }).click();
      await page.locator('[data-testid="history-v2-output-export-preview-1"]').click();
      await expect(overlay.locator('[data-testid="history-v2-export-note"]')).toContainText("Exported to", { timeout: 10000 });
      expect(posts.urls().filter((u) => assetIdOf(u) === "gen_multi_o1_preview").length).toBe(1);

      // Feature output 3, then export output 2's Original: identity unchanged.
      await overlay.getByRole("button", { name: "Output 3 actions" }).click();
      await page.getByRole("button", { name: "Set as featured" }).click();
      await expect(overlay.locator(".comfymodal-studio-history-v2-output-thumb").nth(2)).toHaveClass(
        /featured/, { timeout: 10000 }
      );
      await overlay.getByRole("button", { name: "Output 2 actions" }).click();
      await page.locator('[data-testid="history-v2-output-export-original-1"]').click();
      await expect(overlay.locator('[data-testid="history-v2-export-note"]').last()).toContainText("Exported to", { timeout: 10000 });
      expect(posts.urls().filter((u) => assetIdOf(u) === "gen_multi_o1_orig").length).toBe(1);
      // Never redirected through the featured output's assets.
      expect(posts.urls().filter((u) => assetIdOf(u).startsWith("gen_multi_o2_")).length).toBe(0);
      fx.assertNoConsoleErrors();
    } finally {
      posts.dispose();
      fx.guard.dispose();
    }
  });

  test("10. rerender successor: new Original winner starts not_exported; old export stays historical", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackExportPosts(page);
    try {
      await seedAndOpenHistory(fx, "history_v2_phase_e_original");
      const oldAssetId = "gen_orig_success_old_orig";
      expect((await apiExport(page, fx, oldAssetId)).saved).toBe(true);

      const overlay = await openGenerationDetail(page, "gen_orig_success_original");
      await expect(overlay.locator('[data-testid="history-v2-export-original"]')).toHaveText("Original exported");

      // Generate Again creates a NEW successful Original (O2).
      await overlay.locator('[data-testid="history-v2-generate-again"]').click();
      await expect
        .poll(async () => {
          const item = await getDetailItem(page, fx, "gen_orig_success_original");
          return item.outputs[0].original_asset_id !== oldAssetId;
        }, { timeout: 20000, message: "rerender did not produce a new Original winner" })
        .toBe(true);
      const fresh = await getDetailItem(page, fx, "gen_orig_success_original");
      const newAssetId = fresh.outputs[0].original_asset_id;
      expect(fresh.outputs[0].original_export_state).toBe("not_exported");

      // The polled durable re-render offers Export Original for O2 only.
      const originalBtn = overlay.locator('[data-testid="history-v2-export-original"]');
      await expect(originalBtn).toHaveText("Export Original", { timeout: 15000 });
      await originalBtn.click();
      await expect(originalBtn).toHaveText("Original exported", { timeout: 10000 });
      expect(posts.urls().filter((u) => assetIdOf(u) === newAssetId).length).toBe(1);
      // Old winner's export record remains historical server provenance.
      expect((await exportRecordOf(fx, oldAssetId)).state).toBe("exported");
      fx.assertNoConsoleErrors();
    } finally {
      posts.dispose();
      fx.guard.dispose();
    }
  });

  test("11. failed rerender: retained exported winner keeps its exported state (no false new Export)", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedAndOpenHistory(fx, "history_v2_phase_e");
      const winner = "gen_phase_e_rerender_failed_o0_orig";
      expect((await apiExport(page, fx, winner)).saved).toBe(true);
      const script = await page.request.post("/__comfymodal_test/original-script", {
        data: { sessionId: fx.sessionId, generation_id: "gen_phase_e_rerender_failed", behavior: "fail_always" },
      });
      expect(script.status()).toBe(200);

      const overlay = await openGenerationDetail(page, "gen_phase_e_rerender_failed");
      await expect(overlay.locator('[data-testid="history-v2-export-original"]')).toHaveText("Original exported");

      // A retained usable winner puts the durable phase at "success", so the
      // rerender path is Generate Again (rerender=true) — script it to fail.
      await overlay.locator('[data-testid="history-v2-generate-again"]').click();
      await expect
        .poll(async () => {
          const item = await getDetailItem(page, fx, "gen_phase_e_rerender_failed");
          const last = item.attempts[item.attempts.length - 1];
          return last && last.status === "failed";
        }, { timeout: 20000, message: "scripted rerender failure did not go terminal" })
        .toBe(true);

      // Winner unchanged, still durably exported, no false new Export action.
      const item = await getDetailItem(page, fx, "gen_phase_e_rerender_failed");
      expect(item.outputs[0].original_asset_id).toBe(winner);
      expect(item.outputs[0].original_export_state).toBe("exported");
      await expect(overlay.locator('[data-testid="history-v2-export-original"]')).toHaveText("Original exported", { timeout: 15000 });
      await expect(overlay.locator('[data-testid="history-v2-export-original"]')).toBeDisabled();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});

// ── Experiment cell parity ───────────────────────────────────────────────

test.describe("F10 Configured Export — Experiment cells (fake backend)", () => {

  test("12. cell pane parity: Export Preview/Original target the CELL'S OWN Assets, one POST each", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackExportPosts(page);
    try {
      await seedAndOpenHistory(fx);
      const card = page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_completed"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      await card.click();
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 10000 });

      const cells = page.locator('[data-testid="history-v2-experiment-cell"]');
      await cells.nth(0).focus();
      await page.keyboard.press("Enter");
      const pane = page.locator('[data-testid="history-v2-cell-detail"]');
      await expect(pane).toBeVisible();

      const previewBtn = pane.locator('[data-testid="history-v2-cell-export-preview-exp_completed_cell_0"]');
      const originalBtn = pane.locator('[data-testid="history-v2-cell-export-original-exp_completed_cell_0"]');
      await expect(previewBtn).toHaveText("Export Preview");
      await expect(originalBtn).toHaveText("Export Original");

      await previewBtn.click();
      await expect(page.locator('[data-testid="history-v2-cell-export-note"]')).toContainText("Exported to", { timeout: 10000 });
      await expect(previewBtn).toHaveText("Preview exported", { timeout: 10000 });
      expect(posts.urls().filter((u) => assetIdOf(u) === "exp_completed_c0_preview").length).toBe(1);

      await originalBtn.click();
      await expect(originalBtn).toHaveText("Original exported", { timeout: 10000 });
      expect(posts.urls().filter((u) => assetIdOf(u) === "exp_completed_c0_orig").length).toBe(1);

      // Cell 1 addresses ITS OWN assets — no cross-cell redirect.
      await cells.nth(1).focus();
      await page.keyboard.press("Enter");
      const c1PreviewBtn = pane.locator('[data-testid="history-v2-cell-export-preview-exp_completed_cell_1"]');
      await expect(c1PreviewBtn).toHaveText("Export Preview");
      await c1PreviewBtn.click();
      await expect(c1PreviewBtn).toHaveText("Preview exported", { timeout: 10000 });
      expect(posts.urls().filter((u) => assetIdOf(u) === "exp_completed_c1_preview").length).toBe(1);
      expect(posts.hits.length).toBe(3);
      fx.assertNoConsoleErrors();
    } finally {
      posts.dispose();
      fx.guard.dispose();
    }
  });

  test("13. rapid duplicate click on the SAME asset collapses to exactly one export POST", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackExportPosts(page);
    try {
      await seedAndOpenHistory(fx);
      await page.route("**/history-v2/assets/gen_ok_o0_orig/export", async (route) => {
        await new Promise((r) => setTimeout(r, 400));
        await route.continue();
      });
      const overlay = await openGenerationDetail(page, "gen_ok");
      const originalBtn = overlay.locator('[data-testid="history-v2-export-original"]');
      await expect(originalBtn).toHaveText("Export Original");

      await originalBtn.click();
      await originalBtn.dispatchEvent("click"); // rapid second click mid-flight
      await expect(originalBtn).toHaveText("Original exported", { timeout: 10000 });
      expect(posts.urls().filter((u) => assetIdOf(u) === "gen_ok_o0_orig").length).toBe(1);
      expect(await exportPostCount(fx)).toBe(1);
      fx.assertNoConsoleErrors();
    } finally {
      posts.dispose();
      fx.guard.dispose();
    }
  });
});

// ── Download vs Export distinction ───────────────────────────────────────

test.describe("F10 Download-vs-Export distinction (fake backend)", () => {

  test("14. Browser Download sends ZERO export POSTs and leaves export state untouched", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackExportPosts(page);
    try {
      await seedAndOpenHistory(fx);
      const overlay = await openGenerationDetail(page, "gen_ok");
      const previewBtn = overlay.locator('[data-testid="history-v2-download-preview"]');
      const originalBtn = overlay.locator('[data-testid="history-v2-download-original"]');
      await expect(previewBtn).toHaveText("Download Preview");
      await expect(originalBtn).toHaveText("Download Original");

      const pdl = await captureDownload(page, () => previewBtn.click());
      expect(pdl.name).toContain("preview");
      const odl = await captureDownload(page, () => originalBtn.click());
      expect(odl.name).toContain("original");

      expect(posts.hits.length).toBe(0);
      expect(await exportPostCount(fx)).toBe(0);
      expect(await exportRecordOf(fx, "gen_ok_o0_preview")).toBe(null);
      expect(await exportRecordOf(fx, "gen_ok_o0_orig")).toBe(null);
      const item = await getDetailItem(page, fx, "gen_ok");
      expect(item.outputs[0].preview_export_state).toBe("not_exported");
      expect(item.outputs[0].original_export_state).toBe("not_exported");
      fx.assertNoConsoleErrors();
    } finally {
      posts.dispose();
      fx.guard.dispose();
    }
  });

  test("15. Export causes NO browser download side effect — exactly one POST", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackExportPosts(page);
    let downloadFired = false;
    const onDl = () => { downloadFired = true; };
    page.on("download", onDl);
    try {
      await seedAndOpenHistory(fx);
      const overlay = await openGenerationDetail(page, "gen_preview_only");
      const previewBtn = overlay.locator('[data-testid="history-v2-export-preview"]');
      await expect(previewBtn).toHaveText("Export Preview");

      await previewBtn.click();
      await expect(overlay.locator('[data-testid="history-v2-export-note"]')).toContainText("Exported to", { timeout: 10000 });
      await expect(previewBtn).toHaveText("Preview exported", { timeout: 10000 });
      expect(downloadFired).toBe(false);
      expect(posts.hits.length).toBe(1);
      fx.assertNoConsoleErrors();
    } finally {
      page.off("download", onDl);
      posts.dispose();
      fx.guard.dispose();
    }
  });

  test("16. zero eager Export POSTs: rendering, menus, and View Original stay inert", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackExportPosts(page);
    try {
      await seedAndOpenHistory(fx);
      const overlay = await openGenerationDetail(page, "gen_ok");
      // Open + close the per-output menu (contains Export items).
      await overlay.getByRole("button", { name: "Output 1 actions" }).click();
      await expect(page.locator('[data-testid="history-v2-output-export-preview-0"]')).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.locator('[data-testid="history-v2-output-export-preview-0"]')).toHaveCount(0);
      // View Original display fetch stays export-inert.
      const viewBtn = overlay.locator('[data-testid="history-v2-view-original"]');
      await viewBtn.click();
      await expect(viewBtn).toHaveText("Original loaded", { timeout: 10000 });

      expect(posts.hits.length).toBe(0);
      expect(await exportPostCount(fx)).toBe(0);
      fx.assertNoConsoleErrors();
    } finally {
      posts.dispose();
      fx.guard.dispose();
    }
  });

  test("17. auto-save/local materialization never marks History Export state", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedAndOpenHistory(fx);
      const res = await page.request.post(
        `/comfymodal/run-history/run_seed_0/save?session=${encodeURIComponent(fx.sessionId)}`,
        { data: { output_index: 0 } }
      );
      expect(res.status()).toBe(200);
      const state = await fx.getState();
      expect((state.saveRequests || []).length).toBe(1);
      // Only the explicit /assets/{id}/export route mutates Export state.
      expect(Object.keys(state.exportRecords || {}).length).toBe(0);
      const item = await getDetailItem(page, fx, "gen_ok");
      expect(item.outputs[0].preview_export_state).toBe("not_exported");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});

// ── F5 favoriteOnly fake parity (closes F5 §F5.3) ────────────────────────

test.describe("F10 favoriteOnly mixed-feed production parity (fake backend)", () => {

  test("18. favorites-only mixed feed contains exactly the favorited Generation + favorited Experiment; refresh retains; whole-Experiment favorite keeps working", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedAndOpenHistory(fx);
      // Seed truth: gen_v2_05 is the seeded favorited Generation; favorite
      // one Experiment via the API.  gen_ok / exp_with_failures stay
      // unfavorited as the leak canaries.
      const favExp = await page.request.patch(
        `/comfymodal/history-v2/experiments/exp_completed/favorite?session=${encodeURIComponent(fx.sessionId)}`,
        { data: { favorite: true } }
      );
      expect(favExp.status()).toBe(200);

      await fx.gotoPage("history");
      const chip = page.locator('[data-filter="favoriteOnly"]');
      await chip.click();
      await expect(chip).toHaveAttribute("aria-pressed", "true");

      // Exactly the favorited pair — neither unfavorited record leaks.
      await expect(page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_v2_05"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_completed"]')).toBeVisible();
      await expect(page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_ok"]')).toHaveCount(0);
      await expect(page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_with_failures"]')).toHaveCount(0);

      // Pagination/refresh retains the filter (persisted view state).
      await fx.reload();
      await fx.gotoPage("history");
      await expect(page.locator('[data-filter="favoriteOnly"]')).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      await expect(page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_v2_05"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_completed"]')).toBeVisible();

      // Whole-Experiment favorite continues to work under real UI flow:
      // unfavorite the experiment from its detail page; it leaves the
      // filtered feed while the favorited Generation remains.
      await page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_completed"]').click();
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 10000 });
      const expStar = page.locator(".comfymodal-studio-history-v2-experiment-title-row .comfymodal-studio-history-v2-fav");
      await expect(expStar).toHaveAttribute("aria-pressed", "true");
      await expStar.click();
      await expect(expStar).toHaveAttribute("aria-pressed", "false", { timeout: 10000 });
      await page.locator(".comfymodal-studio-history-v2-back").click();
      await expect(page.locator('[data-filter="favoriteOnly"]')).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      await expect(page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_v2_05"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_completed"]')).toHaveCount(0);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("19. F2A regression: cell favorite stays Generation-backed and independent under favoriteOnly", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      // This seed's experiment cell owns a REAL Generation record, so the
      // F2A Generation-backed cell-favorite semantics are exercisable.
      await seedAndOpenHistory(fx, "history_v2_phase_e_original");
      const favExp = await page.request.patch(
        `/comfymodal/history-v2/experiments/exp_phase_e_original/favorite?session=${encodeURIComponent(fx.sessionId)}`,
        { data: { favorite: true } }
      );
      expect(favExp.status()).toBe(200);

      await fx.gotoPage("history");
      const chip = page.locator('[data-filter="favoriteOnly"]');
      await chip.click();
      await expect(chip).toHaveAttribute("aria-pressed", "true");
      await expect(page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_phase_e_original"]')).toBeVisible({ timeout: 10000 });
      // No Generation is favorited yet.
      await expect(page.locator('.comfymodal-studio-history-v2-generation-card')).toHaveCount(0);

      // Star the CELL → favorites ITS Generation durably (F2A semantics).
      await page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_phase_e_original"]').click();
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 10000 });
      const cells = page.locator('[data-testid="history-v2-experiment-cell"]');
      await cells.nth(0).focus();
      await page.keyboard.press("Enter");
      const cellStar = page.locator('[data-testid="history-v2-cell-favorite"]');
      await expect(cellStar).toHaveAttribute("aria-pressed", "false");
      await cellStar.click();
      await expect(cellStar).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      const state = await fx.getState();
      const cellGen = state.historyV2.find((r) => r.id === "gen_phase_e_original_cell_0");
      expect(cellGen.favorite).toBe(true);
      const exp = state.historyV2.find((r) => r.id === "exp_phase_e_original");
      expect(exp.favorite).toBe(true);

      // Filtered mixed feed now shows BOTH favorited records independently.
      await page.locator(".comfymodal-studio-history-v2-back").click();
      await expect(page.locator('[data-filter="favoriteOnly"]')).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      await expect(page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_phase_e_original_cell_0"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_phase_e_original"]')).toBeVisible();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
