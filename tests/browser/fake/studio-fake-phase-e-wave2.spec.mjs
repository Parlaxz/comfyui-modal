// Phase-E Wave-2 logical-output and History presentation coverage.
//
// The fake seed mirrors the expected additive projection. Passing tests prove
// deterministic API/UI state handling only, not production persistence,
// codec execution, remote Modal reads, or Generate Original routing.

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const IDS = {
  logical: "gen_phase_e_wave2_logical",
  retry: "gen_phase_e_wave2_retry",
  two: "gen_phase_e_wave2_two",
  previewOnly: "gen_phase_e_wave2_preview_only",
  featuredThumbnail: "gen_phase_e_wave2_featured_thumbnail",
  featuredPreview: "gen_phase_e_wave2_featured_preview",
  featuredOlderOriginal: "gen_phase_e_wave2_featured_older_original",
  remoteOnly: "gen_phase_e_wave2_remote_only",
  experiment: "exp_phase_e_wave2",
};

async function seedWave2(fx) {
  const seeded = await fx.seedHistory("history_v2_phase_e_wave2");
  expect(seeded).toMatchObject({ status: "ok", scenario: "history_v2_phase_e_wave2", v2: true });
  expect(seeded.count).toBe(9);
}

async function getGeneration(page, sessionId, id) {
  const res = await page.request.get(
    `/comfymodal/history-v2/generations/${id}?session=${encodeURIComponent(sessionId)}`,
  );
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.status).toBe("ok");
  return body.item;
}

async function getAsset(page, url, sessionId) {
  const res = await page.request.get(`${url}?session=${encodeURIComponent(sessionId)}`);
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toMatch(/^image\/png/);
  expect((await res.body()).length).toBeGreaterThan(20);
}

async function openGeneration(page, id) {
  await page.locator(`.comfymodal-studio-history-v2-generation-card[data-id="${id}"]`).click();
  const overlay = page.locator('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]');
  await expect(overlay).toBeVisible({ timeout: 10000 });
  return overlay;
}

test.describe("Studio Phase-E Wave-2 harness (fake backend)", () => {
  test("logical derivatives remain one output and retain all Attempt provenance", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedWave2(fx);
      const item = await getGeneration(page, fx.sessionId, IDS.logical);
      const output = item.outputs[0];

      expect(item.output_count).toBe(1);
      expect(item.outputs).toHaveLength(1);
      expect(output.logical_output_key).toBe("gen_wave2_logical_o0");
      expect(output.attempt_ids).toEqual([
        "run_wave2_preview", "run_wave2_original_old", "run_wave2_original_new",
      ]);
      expect(output.asset_provenance.map((entry) => entry.asset_type)).toEqual([
        "thumbnail", "preview", "original", "original",
      ]);
      expect(output.original_urls).toHaveLength(2);
      expect(output.original_url).toContain("gen_wave2_logical_new_orig");
      for (const url of [output.thumb_url, output.preview_url, output.original_url]) await getAsset(page, url, fx.sessionId);

      await fx.gotoPage("history");
      const overlay = await openGeneration(page, IDS.logical);
      await expect(overlay.locator(".comfymodal-studio-history-v2-output-thumb")).toHaveCount(1);
      await expect(overlay.locator(".comfymodal-studio-history-v2-attempt")).toHaveCount(3);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("output_count counts two logical keys, not five derivative assets", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedWave2(fx);
      const item = await getGeneration(page, fx.sessionId, IDS.two);
      expect(item.output_count).toBe(2);
      expect(item.outputs).toHaveLength(2);
      expect(new Set(item.outputs.map((output) => output.logical_output_key)).size).toBe(2);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("Preview Attempt exposes WebP/70 metadata and Preview remains distinct", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedWave2(fx);
      const item = await getGeneration(page, fx.sessionId, IDS.logical);
      const previewAttempt = item.attempts.find((attempt) => attempt.mode === "preview");
      expect(previewAttempt).toMatchObject({ mode: "preview", status: "completed", codec: "webp", quality: 70 });
      expect(item.outputs[0]).toMatchObject({ preview_codec: "webp", preview_quality: 70 });
      expect(item.outputs[0].thumb_url).not.toBe(item.outputs[0].preview_url);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("failed Original retry retains Preview and prefers newest successful Original", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedWave2(fx);
      const item = await getGeneration(page, fx.sessionId, IDS.retry);
      expect(item.attempts.map((attempt) => [attempt.mode, attempt.status])).toEqual([
        ["preview", "completed"], ["original", "failed"], ["original", "completed"],
      ]);
      expect(item.outputs[0].preview_url).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      expect(item.outputs[0].original_url).toContain("gen_wave2_retry_orig");
      expect(item.outputs[0].original_failed).toBe(false);
      expect(item.errors).toEqual([{ code: "attempt_failed", message: "Original upload failed" }]);
      await fx.gotoPage("history");
      const overlay = await openGeneration(page, IDS.retry);
      await expect(overlay).toContainText("Original upload failed");
      await expect(overlay.locator('[data-testid="history-v2-original-failed-badge"]')).toHaveCount(0);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("featured Thumbnail, Preview, and older Original resolve by logical output index", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedWave2(fx);
      const expected = [
        [IDS.featuredThumbnail, 0, "gen_phase_e_wave2_featured_thumbnail_o0"],
        [IDS.featuredPreview, 1, "gen_phase_e_wave2_featured_preview_o1"],
        [IDS.featuredOlderOriginal, 1, "gen_phase_e_wave2_featured_older_original_o1"],
      ];
      for (const [id, index, logicalKey] of expected) {
        const item = await getGeneration(page, fx.sessionId, id);
        expect(item.featured_output_index).toBe(index);
        expect(item.outputs[index].logical_output_key).toBe(logicalKey);
        if (id === IDS.featuredOlderOriginal) {
          expect(item.outputs[index].original_url).toContain("new_orig");
        }
      }
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("remote Original-only record does not auto-fetch in feed but loads explicitly in detail", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const requests = [];
    page.on("request", (request) => {
      if (request.url().includes("/comfymodal/history-v2/assets/")) requests.push(request.url());
    });
    try {
      await seedWave2(fx);
      const item = await getGeneration(page, fx.sessionId, IDS.remoteOnly);
      expect(item.outputs[0].thumb_url).toBe("");
      expect(item.outputs[0].preview_url).toBe("");
      expect(item.outputs[0].original_url).toContain("gen_wave2_remote_only_orig");
      expect(item.outputs[0].original_failed).toBe(false);
      await getAsset(page, item.outputs[0].original_url, fx.sessionId);

      await fx.gotoPage("history");
      const feedRequests = requests.slice();
      expect(feedRequests.some((url) => url.includes("gen_wave2_remote_only_orig"))).toBe(false);
      const card = page.locator(`.comfymodal-studio-history-v2-generation-card[data-id="${IDS.remoteOnly}"]`);
      await expect(card).toContainText("Original available");
      const overlay = await openGeneration(page, IDS.remoteOnly);
      await overlay.getByTestId("history-v2-view-original").click();
      const original = overlay.locator(".comfymodal-studio-history-v2-original-img");
      await expect(original).toBeVisible();
      await expect(original).toHaveAttribute("src", /gen_wave2_remote_only_orig/);
      expect(requests.some((url) => url.includes("gen_wave2_remote_only_orig"))).toBe(true);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("Preview-only card exposes a Preview badge", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedWave2(fx);
      await fx.gotoPage("history");
      const card = page.locator(`.comfymodal-studio-history-v2-generation-card[data-id="${IDS.previewOnly}"]`);
      await expect(card.locator('[data-testid="history-v2-preview-badge"]')).toBeVisible();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("Experiment detail preserves frozen Preview options and stable cell Generations", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedWave2(fx);
      const res = await page.request.get(
        `/comfymodal/history-v2/experiments/${IDS.experiment}?session=${encodeURIComponent(fx.sessionId)}`,
      );
      expect(res.status()).toBe(200);
      const body = await res.json();
      expect(body.item.modal_options).toEqual({ enabled: true, codec: "webp", quality: 70 });
      expect(body.item.cells.map((cell) => cell.generation_id)).toEqual([
        "gen_phase_e_wave2_cell_0", "gen_phase_e_wave2_cell_1",
      ]);
      expect(body.item.concurrency).toBeUndefined();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
