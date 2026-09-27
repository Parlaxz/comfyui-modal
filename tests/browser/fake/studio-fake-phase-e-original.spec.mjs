// Phase-E Generate Original (E3B2 route mirror) deterministic coverage.
//
// The fake backend implements the frozen production contract for
// POST /comfymodal/history-v2/generations/{generation_id}/original and
// POST .../original/retry and mirrors history_v2_replay.decide_original_action
// exactly. These tests prove the cross-layer state machine (fake API + real
// web/ frontend modules): same-Generation new Attempts, logical-output
// identity, the E4D three-way action distinction (Generate Original vs
// dedicated bodyless Retry vs Generate Again rerender:true), busy/
// irreproducible refusals, and no-eager-Original display.
// They do NOT prove SQLite persistence, canonical execution, or remote
// Modal output — those stay production-lane evidence.

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const IDS = {
  create: "gen_orig_preview_only",
  active: "gen_orig_active_original",
  success: "gen_orig_success_original",
  retry: "gen_orig_failed_original",
  busy: "gen_orig_busy_preview",
  irreproducible: "gen_orig_irreproducible",
  cellGeneration: "gen_phase_e_original_cell_0",
  experiment: "exp_phase_e_original",
};

const OLD_SUCCESS_ORIG = "gen_orig_success_old_orig";

async function seedOriginal(fx) {
  const seeded = await fx.seedHistory("history_v2_phase_e_original");
  expect(seeded).toMatchObject({ status: "ok", scenario: "history_v2_phase_e_original", v2: true });
  expect(seeded.count).toBe(8);
}

async function postOriginal(page, sessionId, id, body) {
  return page.request.post(
    `/comfymodal/history-v2/generations/${id}/original?session=${encodeURIComponent(sessionId)}`,
    { data: body || {} },
  );
}

async function getDetail(page, sessionId, id) {
  const res = await page.request.get(
    `/comfymodal/history-v2/generations/${id}?session=${encodeURIComponent(sessionId)}`
  );
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.status).toBe("ok");
  return body.item;
}

async function pollTerminal(page, sessionId, id, runId, status) {
  await expect.poll(async () => {
    const item = await getDetail(page, sessionId, id);
    const attempt = item.attempts.find((a) => a.run_id === runId);
    return attempt ? attempt.status : "";
  }, { timeout: 15000, message: `attempt ${runId} never reached ${status}` }).toBe(status);
}

async function openGeneration(page, id) {
  await page.locator(`.comfymodal-studio-history-v2-generation-card[data-id="${id}"]`).click();
  const overlay = page.locator('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]');
  await expect(overlay).toBeVisible({ timeout: 10000 });
  return overlay;
}

test.describe("Studio Phase-E Generate Original harness (fake backend)", () => {
  test("create queues one Original under the SAME Generation and one logical output", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedOriginal(fx);
      const before = await getDetail(page, fx.sessionId, IDS.create);
      expect(before.output_count).toBe(1);
      const previewUrl = before.outputs[0].preview_url;
      const logicalKey = before.outputs[0].logical_output_key;

      const res = await postOriginal(page, fx.sessionId, IDS.create);
      expect(res.status()).toBe(200);
      const body = await res.json();
      // Landed E3B2 created payload (pinned by
      // tests/test_history_v2_generate_original.py).
      expect(Object.keys(body).sort()).toEqual([
        "attempt_status", "decision", "executor", "generation_id",
        "outcome", "purpose", "reason", "reused", "run_id", "status",
      ]);
      expect(body).toMatchObject({
        status: "ok",
        generation_id: IDS.create,
        purpose: "original",
        decision: "create_original",
        reason: "no_successful_or_active_original",
        outcome: "original_created",
        attempt_status: "queued",
        reused: false,
        executor: "canonical_execution.execute_plan",
      });

      // Same Generation identity: attempts append, no second Generation.
      const mid = await getDetail(page, fx.sessionId, IDS.create);
      expect(mid.id).toBe(IDS.create);
      expect(mid.attempts.map((a) => [a.mode, a.status])).toEqual([
        ["preview", "completed"],
        ["original", expect.stringMatching(/^(queued|running)$/)],
      ]);
      const feedRes = await page.request.get(
        `/comfymodal/history-v2/feed?kind=generation&search=${IDS.create}&session=${encodeURIComponent(fx.sessionId)}`
      );
      const feed = (await feedRes.json()).items.filter((i) => i.id === IDS.create);
      expect(feed).toHaveLength(1);

      await pollTerminal(page, fx.sessionId, IDS.create, body.run_id, "completed");
      const done = await getDetail(page, fx.sessionId, IDS.create);
      expect(done.output_count).toBe(1);
      expect(done.outputs[0].logical_output_key).toBe(logicalKey);
      expect(done.outputs[0].preview_url).toBe(previewUrl);
      expect(done.outputs[0].original_url).toContain("/comfymodal/history-v2/assets/");
      expect(done.attempts.map((a) => a.mode)).toEqual(["preview", "original"]);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("active Original reuse serializes duplicates onto the existing Attempt", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedOriginal(fx);
      const before = await getDetail(page, fx.sessionId, IDS.active);
      expect(before.attempts).toHaveLength(2);

      for (let i = 0; i < 2; i++) {
        const res = await postOriginal(page, fx.sessionId, IDS.active);
        expect(res.status()).toBe(200);
        expect(await res.json()).toMatchObject({
          status: "ok",
          outcome: "original_already_active",
          decision: "reuse_active",
          reason: "original_attempt_active",
          run_id: "run_orig_active_running",
          attempt_status: "running",
          reused: true,
        });
      }
      const after = await getDetail(page, fx.sessionId, IDS.active);
      expect(after.attempts).toHaveLength(2);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("successful reuse returns the newest success without spending execution", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedOriginal(fx);
      const res = await postOriginal(page, fx.sessionId, IDS.success);
      expect(res.status()).toBe(200);
      expect(await res.json()).toMatchObject({
        status: "ok",
        outcome: "original_already_completed",
        decision: "reuse_successful",
        reason: "newest_successful_original",
        run_id: "run_orig_success_old",
        attempt_status: "completed",
        reused: true,
      });
      const after = await getDetail(page, fx.sessionId, IDS.success);
      expect(after.attempts).toHaveLength(2);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("explicit rerender creates a new Attempt and prefers the newest success", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedOriginal(fx);
      const res = await postOriginal(page, fx.sessionId, IDS.success, { rerender: true });
      expect(res.status()).toBe(200);
      const body = await res.json();
      expect(body).toMatchObject({
        status: "ok",
        outcome: "original_created",
        decision: "create_original",
        reason: "explicit_rerender",
        reused: false,
      });
      expect(body.run_id).not.toBe("run_orig_success_old");

      await pollTerminal(page, fx.sessionId, IDS.success, body.run_id, "completed");
      const done = await getDetail(page, fx.sessionId, IDS.success);
      expect(done.output_count).toBe(1);
      expect(done.outputs[0].original_urls).toHaveLength(2);
      expect(done.outputs[0].attempt_ids).toContain(body.run_id);
      expect(done.outputs[0].original_url).toContain(body.run_id.slice(-4));
      expect(done.outputs[0].original_url).not.toContain(OLD_SUCCESS_ORIG);
      // The earlier successful Original stays retained.
      const oldAsset = await page.request.get(
        `/comfymodal/history-v2/assets/${OLD_SUCCESS_ORIG}?session=${encodeURIComponent(fx.sessionId)}`
      );
      expect(oldAsset.status()).toBe(200);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("failed rerender keeps the earlier usable Original available", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedOriginal(fx);
      const scripted = await page.request.post("/__comfymodal_test/original-script", {
        data: { sessionId: fx.sessionId, generation_id: IDS.success, behavior: "fail_once", error: "Rerender timed out" },
      });
      expect((await scripted.json()).status).toBe("ok");

      const res = await postOriginal(page, fx.sessionId, IDS.success, { rerender: true });
      expect(res.status()).toBe(200);
      const body = await res.json();
      await pollTerminal(page, fx.sessionId, IDS.success, body.run_id, "failed");

      const done = await getDetail(page, fx.sessionId, IDS.success);
      expect(done.errors.some((e) => e.message === "Rerender timed out")).toBe(true);
      // Older usable Original remains the preferred available asset.
      expect(done.outputs[0].original_url).toContain(OLD_SUCCESS_ORIG);
      expect(done.outputs[0].original_failed).toBe(false);
      const oldAsset = await page.request.get(
        `/comfymodal/history-v2/assets/${OLD_SUCCESS_ORIG}?session=${encodeURIComponent(fx.sessionId)}`
      );
      expect(oldAsset.status()).toBe(200);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("failed-only reports retry_required; the explicit retry route creates", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedOriginal(fx);
      // POST /original never silently reinterprets Generate Original as
      // Retry: failed-only history reports retry_required with zero writes.
      const res = await postOriginal(page, fx.sessionId, IDS.retry);
      expect(res.status()).toBe(200);
      expect(await res.json()).toMatchObject({
        status: "ok",
        outcome: "retry_required",
        decision: "retry_required",
        reason: "only_failed_original_attempts",
        run_id: "run_orig_retry_failed",
        attempt_status: "failed",
        reused: false,
      });
      let done = await getDetail(page, fx.sessionId, IDS.retry);
      expect(done.attempts).toHaveLength(2);

      // The explicit retry route creates ONE queued Attempt under the SAME
      // Generation and retains the failed one untouched.
      const retryRes = await page.request.post(
        `/comfymodal/history-v2/generations/${IDS.retry}/original/retry?session=${encodeURIComponent(fx.sessionId)}`,
        { data: {} },
      );
      expect(retryRes.status()).toBe(200);
      const retryBody = await retryRes.json();
      expect(retryBody).toMatchObject({
        status: "ok",
        outcome: "original_created",
        decision: "create_original",
        reason: "original_retry",
        reused: false,
      });

      await pollTerminal(page, fx.sessionId, IDS.retry, retryBody.run_id, "completed");
      done = await getDetail(page, fx.sessionId, IDS.retry);
      expect(done.attempts.map((a) => [a.mode, a.status])).toEqual([
        ["preview", "completed"],
        ["original", "failed"],
        ["original", "completed"],
      ]);
      expect(done.attempts[1].error).toBe("Original replay failed");
      expect(done.outputs[0].original_failed).toBe(false);
      expect(done.outputs[0].original_url).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      expect(done.outputs[0].preview_url).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      // Same-Generation retry proof from durable state: Attempt B is a NEW
      // run id under the SAME Generation, failed A remains, Preview remains,
      // and the logical output count never inflated because B exists.
      expect(retryBody.run_id).not.toBe("run_orig_retry_failed");
      expect(done.id).toBe(IDS.retry);
      expect(done.output_count).toBe(1);
      const retryFeedRes = await page.request.get(
        `/comfymodal/history-v2/feed?kind=generation&search=${IDS.retry}&session=${encodeURIComponent(fx.sessionId)}`
      );
      const retryFeed = (await retryFeedRes.json()).items.filter((i) => i.id === IDS.retry);
      expect(retryFeed).toHaveLength(1);
      const previewAfterRetry = await page.request.get(
        `${done.outputs[0].preview_url}?session=${encodeURIComponent(fx.sessionId)}`
      );
      expect(previewAfterRetry.status()).toBe(200);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("retry route refuses when nothing is retryable or attempts are active", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedOriginal(fx);
      // No original attempt at all → not retryable.
      const noOriginal = await page.request.post(
        `/comfymodal/history-v2/generations/${IDS.create}/original/retry?session=${encodeURIComponent(fx.sessionId)}`,
        { data: {} },
      );
      expect(noOriginal.status()).toBe(409);
      expect(await noOriginal.json()).toMatchObject({
        status: "error",
        code: "retry_not_available",
      });
      // A successful original is not a retry candidate.
      const successRetry = await page.request.post(
        `/comfymodal/history-v2/generations/${IDS.success}/original/retry?session=${encodeURIComponent(fx.sessionId)}`,
        { data: {} },
      );
      expect(successRetry.status()).toBe(409);
      expect(await successRetry.json()).toMatchObject({
        status: "error",
        code: "retry_not_available",
      });
      // Any active attempt on the generation makes retry busy.
      const activeRetry = await page.request.post(
        `/comfymodal/history-v2/generations/${IDS.active}/original/retry?session=${encodeURIComponent(fx.sessionId)}`,
        { data: {} },
      );
      expect(activeRetry.status()).toBe(409);
      expect(await activeRetry.json()).toMatchObject({
        status: "error",
        code: "generation_busy",
      });
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("busy generation refuses with a machine-readable outcome and zero writes", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedOriginal(fx);
      const before = await getDetail(page, fx.sessionId, IDS.busy);
      const res = await postOriginal(page, fx.sessionId, IDS.busy);
      expect(res.status()).toBe(409);
      const body = await res.json();
      expect(body.status).toBe("error");
      expect(body.code).toBe("generation_busy");
      expect(body.decision).toBe("busy");
      expect(body.reason).toBe("preview_attempt_active");
      const after = await getDetail(page, fx.sessionId, IDS.busy);
      expect(after.attempts.length).toBe(before.attempts.length);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("irreproducible legacy snapshot refuses without any Attempt write", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedOriginal(fx);
      const before = await getDetail(page, fx.sessionId, IDS.irreproducible);
      const res = await postOriginal(page, fx.sessionId, IDS.irreproducible);
      expect(res.status()).toBe(409);
      const body = await res.json();
      expect(body.code).toBe("generation_not_reproducible");
      expect(body.reason).toBe("missing_request_snapshot");
      const after = await getDetail(page, fx.sessionId, IDS.irreproducible);
      expect(JSON.stringify(after.attempts)).toBe(JSON.stringify(before.attempts));
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("execution failure retains Preview and invents no Original asset", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedOriginal(fx);
      const scripted = await page.request.post("/__comfymodal_test/original-script", {
        data: { sessionId: fx.sessionId, generation_id: IDS.create, behavior: "fail_always", error: "Original upload failed" },
      });
      expect((await scripted.json()).status).toBe("ok");

      const res = await postOriginal(page, fx.sessionId, IDS.create);
      expect(res.status()).toBe(200);
      const body = await res.json();
      expect(body.outcome).toBe("original_created");
      await pollTerminal(page, fx.sessionId, IDS.create, body.run_id, "failed");

      const done = await getDetail(page, fx.sessionId, IDS.create);
      expect(done.outputs[0].original_url).toBe("");
      expect(done.outputs[0].original_failed).toBe(true);
      // Preview is untouched and still served.
      expect(done.outputs[0].preview_url).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      const preview = await page.request.get(
        `${done.outputs[0].preview_url}?session=${encodeURIComponent(fx.sessionId)}`
      );
      expect(preview.status()).toBe(200);
      expect((await preview.body()).length).toBeGreaterThan(20);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("detail UI: Generate Original keeps Preview, then surfaces View Original", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedOriginal(fx);
      await fx.gotoPage("history");
      const overlay = await openGeneration(page, IDS.create);

      const btn = overlay.getByTestId("history-v2-generate-original");
      await expect(btn).toBeEnabled();
      await btn.click();

      // Queued phase: truthful note, disabled control, Preview never replaced.
      const note = overlay.getByTestId("history-v2-generate-note");
      await expect(note).toContainText("Preview retained");
      await expect(overlay.locator('img[alt="Preview"], img.comfymodal-studio-history-v2-featured-img').first())
        .toBeVisible();

      // Polling reaches terminal success; the action becomes explicit rerender.
      const again = overlay.getByTestId("history-v2-generate-again");
      await expect(again).toBeVisible({ timeout: 20000 });
      await expect(note).toContainText("View Original");

      // Explicit View Original triggers the only full-asset GET.
      await overlay.getByTestId("history-v2-view-original").click();
      await expect(overlay.locator('img[alt="Original"]')).toBeVisible();
      await expect(overlay.locator('img[alt="Preview"]')).toBeVisible();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("detail UI: failed-only state never auto-retries; explicit Retry POSTs only /original/retry", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const ordinaryOriginalPosts = [];
    const retryPosts = [];
    page.on("request", (request) => {
      if (request.method() !== "POST") return;
      const url = request.url();
      if (!url.includes("/comfymodal/history-v2/generations/")) return;
      if (url.includes("/original/retry")) retryPosts.push(url);
      else if (url.endsWith("/original")) ordinaryOriginalPosts.push(url);
    });
    try {
      await seedOriginal(fx);
      await fx.gotoPage("history");
      const overlay = await openGeneration(page, IDS.retry);

      // E4D: rendering a failed-only Generation fires NO Original request at
      // all — retry_required is a state, not an action; the explicit Retry
      // control is offered instead.
      const retryBtn = overlay.getByTestId("history-v2-retry-original");
      await expect(retryBtn).toBeVisible();
      await expect(retryBtn).toBeEnabled();
      await expect(overlay.getByTestId("history-v2-generate-note")).toContainText("Original failed");
      expect(ordinaryOriginalPosts).toHaveLength(0);
      expect(retryPosts).toHaveLength(0);

      // The click performs exactly ONE dedicated /original/retry POST and
      // ZERO ordinary /original POSTs.
      await retryBtn.click();
      await expect.poll(() => retryPosts.length, { timeout: 10000 }).toBe(1);
      expect(retryPosts[0]).toContain(`/generations/${IDS.retry}/original/retry`);
      expect(ordinaryOriginalPosts).toHaveLength(0);

      // Durable fake backend state: SAME Generation gains ONE new queued/
      // running Original Attempt while the failed Attempt remains retained.
      let firstSeen = null;
      await expect.poll(async () => {
        const item = await getDetail(page, fx.sessionId, IDS.retry);
        if (item.attempts.length === 3 && !firstSeen) firstSeen = item;
        return item.attempts.length;
      }, { timeout: 15000 }).toBe(3);
      expect(firstSeen.id).toBe(IDS.retry);
      expect(firstSeen.output_count).toBe(1);
      expect(firstSeen.attempts[1].run_id).toBe("run_orig_retry_failed");
      expect(firstSeen.attempts[1].status).toBe("failed");
      expect(firstSeen.attempts[1].error).toBe("Original replay failed");
      expect(firstSeen.attempts[2].mode).toBe("original");
      expect(firstSeen.attempts[2].status).toMatch(/^(queued|running)$/);
      expect(firstSeen.attempts[2].run_id).not.toBe("run_orig_retry_failed");
      // Preview asset remains served throughout the retry.
      const previewDuringRetry = await page.request.get(
        `${firstSeen.outputs[0].preview_url}?session=${encodeURIComponent(fx.sessionId)}`
      );
      expect(previewDuringRetry.status()).toBe(200);

      // Polling reaches terminal success; the new Attempt attaches an
      // Original under the SAME logical output without inflating it.
      const feedRes = await page.request.get(
        `/comfymodal/history-v2/feed?kind=generation&search=${IDS.retry}&session=${encodeURIComponent(fx.sessionId)}`
      );
      const feed = (await feedRes.json()).items.filter((i) => i.id === IDS.retry);
      expect(feed).toHaveLength(1);
      const doneItem = await getDetail(page, fx.sessionId, IDS.retry);
      const newest = doneItem.attempts[doneItem.attempts.length - 1];
      await pollTerminal(page, fx.sessionId, IDS.retry, newest.run_id, "completed");
      const done = await getDetail(page, fx.sessionId, IDS.retry);
      expect(done.id).toBe(IDS.retry);
      expect(done.attempts.map((a) => [a.mode, a.status])).toEqual([
        ["preview", "completed"],
        ["original", "failed"],
        ["original", "completed"],
      ]);
      expect(done.output_count).toBe(1);
      expect(done.outputs[0].logical_output_key).toBe(firstSeen.outputs[0].logical_output_key);
      expect(done.outputs[0].original_failed).toBe(false);
      expect(done.outputs[0].original_url).toContain(newest.run_id.slice(-4));
      expect(done.outputs[0].preview_url).toBe(firstSeen.outputs[0].preview_url);

      // Success does NOT eagerly fetch full Original bytes; only the explicit
      // View Original action performs that fetch.
      const originalAssetFetches = [];
      page.on("request", (request) => {
        if (
          request.method() === "GET"
          && request.url().includes("/comfymodal/history-v2/assets/")
          && request.url().includes(newest.run_id.slice(-4))
        ) {
          originalAssetFetches.push(request.url());
        }
      });
      await expect(overlay.getByTestId("history-v2-generate-again")).toBeVisible({ timeout: 20000 });
      await expect(overlay.getByTestId("history-v2-generate-note")).toContainText("View Original");
      expect(originalAssetFetches).toHaveLength(0);
      await overlay.getByTestId("history-v2-view-original").click();
      await expect(overlay.locator('img[alt="Original"]')).toBeVisible();
      await expect(overlay.locator('img[alt="Preview"], img.comfymodal-studio-history-v2-featured-img').first())
        .toBeVisible();
      expect(originalAssetFetches.length).toBeGreaterThanOrEqual(1);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("detail UI: Retry Original completes a new successful Attempt in the rendered detail", async ({ page }) => {
    // Retired fixme (E5D2): E4D landed the dedicated /original/retry seam, so
    // this scenario now executes end to end against the real frontend module:
    // user Retry → one bodyless /original/retry POST → durable polling renders
    // the appended Attempt → terminal success keeps the failed Attempt and the
    // Preview visible while Generate Again becomes the next action.
    const fx = await setupFakeTest(page);
    try {
      await seedOriginal(fx);
      await fx.gotoPage("history");
      const overlay = await openGeneration(page, IDS.retry);
      await overlay.getByTestId("history-v2-retry-original").click();

      // Durable polling renders the appended Attempt as active: the note
      // reports its queued/running status while Preview stays retained.
      await expect(overlay.getByTestId("history-v2-generate-note"))
        .toContainText(/Original attempt (queued|running)/, { timeout: 10000 });

      // Durable polling re-renders the appended Attempt (3 total) while the
      // failed Attempt text stays visible and Preview is never replaced.
      const attempts = overlay.locator(".comfymodal-studio-history-v2-attempt");
      await expect(attempts).toHaveCount(3, { timeout: 20000 });
      await expect(overlay).toContainText("Original replay failed");
      await expect(overlay.locator('img[alt="Preview"], img.comfymodal-studio-history-v2-featured-img').first())
        .toBeVisible();

      // Terminal success flips the action to explicit rerender (Generate
      // Again) and surfaces View Original — no eager Original load happened.
      const again = overlay.getByTestId("history-v2-generate-again");
      await expect(again).toBeVisible({ timeout: 20000 });
      await expect(overlay.getByTestId("history-v2-generate-note")).toContainText("View Original");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("detail UI: Generate Again is the only rerender path (/original + rerender:true)", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const ordinaryOriginalPosts = [];
    const retryPosts = [];
    page.on("request", (request) => {
      if (request.method() !== "POST") return;
      const url = request.url();
      if (!url.includes("/comfymodal/history-v2/generations/")) return;
      if (url.includes("/original/retry")) retryPosts.push({ url, body: request.postData() });
      else if (url.endsWith("/original")) {
        ordinaryOriginalPosts.push({ url, body: request.postData() });
      }
    });
    try {
      await seedOriginal(fx);
      await fx.gotoPage("history");
      const overlay = await openGeneration(page, IDS.success);

      // A successful Original spends nothing on open: no automatic rerender,
      // no retry probe.
      const again = overlay.getByTestId("history-v2-generate-again");
      await expect(again).toBeVisible();
      expect(ordinaryOriginalPosts).toHaveLength(0);
      expect(retryPosts).toHaveLength(0);

      // Generate Again posts ordinary /original with rerender:true — never
      // the retry route, never a bare create.
      await again.click();
      await expect.poll(() => ordinaryOriginalPosts.length, { timeout: 10000 }).toBe(1);
      expect(ordinaryOriginalPosts[0].url).toContain(`/generations/${IDS.success}/original`);
      expect(JSON.parse(ordinaryOriginalPosts[0].body)).toEqual({ rerender: true });
      expect(retryPosts).toHaveLength(0);

      // The rerender Attempt completes; newest success wins and the earlier
      // successful Original stays retained underneath the same group.
      const created = await getDetail(page, fx.sessionId, IDS.success);
      const newest = created.attempts[created.attempts.length - 1];
      expect(newest.mode).toBe("original");
      expect(newest.run_id).not.toBe("run_orig_success_old");
      await pollTerminal(page, fx.sessionId, IDS.success, newest.run_id, "completed");
      const done = await getDetail(page, fx.sessionId, IDS.success);
      expect(done.output_count).toBe(1);
      expect(done.outputs[0].original_url).toContain(newest.run_id.slice(-4));
      const oldAsset = await page.request.get(
        `/comfymodal/history-v2/assets/${OLD_SUCCESS_ORIG}?session=${encodeURIComponent(fx.sessionId)}`
      );
      expect(oldAsset.status()).toBe(200);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("experiment cell action targets the cell's own Generation through the frozen route", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const originalPosts = [];
    page.on("request", (request) => {
      if (
        request.method() === "POST"
        && request.url().includes("/comfymodal/history-v2/generations/")
        && request.url().endsWith("/original")
      ) {
        originalPosts.push(request.url());
      }
    });
    try {
      await seedOriginal(fx);
      await fx.gotoPage("history");
      const card = page.locator(`.comfymodal-studio-history-v2-experiment-card[data-id="${IDS.experiment}"]`);
      await expect(card).toBeVisible({ timeout: 15000 });
      await card.click();
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 10000 });

      const cells = page.locator('[data-testid="history-v2-experiment-cell"]');
      await expect(cells).toHaveCount(1);
      await cells.nth(0).focus();
      await page.keyboard.press("Enter");
      await expect(page.locator('[data-testid="history-v2-cell-detail"]')).toBeVisible();

      const cellBtn = page.locator(
        `[data-testid="history-v2-cell-detail-generate-original-${IDS.experiment}_cell_0"]`
      );
      await expect(cellBtn).toBeVisible();
      await expect(cellBtn).toBeEnabled();
      await cellBtn.click();

      // Exactly one POST to the CELL'S OWN generation id — same frozen route.
      await expect.poll(() => originalPosts.length, { timeout: 10000 }).toBe(1);
      expect(originalPosts[0]).toContain(`/generations/${IDS.cellGeneration}/original`);

      // Same Generation gains the new Original Attempt; no second Generation.
      await expect.poll(async () => {
        const gen = await getDetail(page, fx.sessionId, IDS.cellGeneration);
        return gen.attempts.filter((a) => a.mode === "original").length;
      }, { timeout: 15000 }).toBeGreaterThanOrEqual(1);
      const gen = await getDetail(page, fx.sessionId, IDS.cellGeneration);
      expect(gen.id).toBe(IDS.cellGeneration);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
