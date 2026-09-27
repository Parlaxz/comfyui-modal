// Phase F6 — Single Resume UI + truthful Retry naming deterministic coverage.
//
// Proves the mounted History V2 frontend against the fake backend's F1A
// resume route mirror: interrupted-only eligibility, exactly one bodyless
// POST to the frozen route, durable refresh driving state (no optimistic
// Attempt fabrication), Preview-interrupted Resume never invoking /original,
// refusal recovery, and the conditional Retry run / Retry Original labels.
//
// Download coverage for this lane lives in
// studio-fake-history-v2-download.spec.mjs (concurrent writer, same batch).

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const IDS = {
  resumePreview: "gen_f6_resume_preview",
  retryRun: "gen_f6_retry_run_plain",
  blockedIrreproducible: "gen_f6_resume_blocked",
  replayFalse: "gen_f6_resume_replay_false",
  canceled: "gen_f6_canceled",
  completed: "gen_f6_completed",
};

async function seedF6(fx) {
  const seeded = await fx.seedHistory("history_v2_phase_f6_resume");
  expect(seeded).toMatchObject({ status: "ok", scenario: "history_v2_phase_f6_resume", v2: true });
  await fx.reload();
}

/** Enable a status filter chip ("Failed" / "Canceled") when not already pressed. */
async function enableStatus(page, label) {
  const target = page.getByRole("button", { name: label, exact: true });
  await expect(target).toBeVisible({ timeout: 10000 });
  if ((await target.getAttribute("aria-pressed")) !== "true") {
    await target.click();
    await expect(target).toHaveAttribute("aria-pressed", "true");
  }
}

async function openGeneration(page, id) {
  await page.locator(`.comfymodal-studio-history-v2-generation-card[data-id="${id}"]`).click();
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

function trackGenerationsPosts(page) {
  const posts = { resume: [], original: [], retry: [] };
  page.on("request", (r) => {
    if (r.method() !== "POST") return;
    const url = r.url();
    if (!url.includes("/comfymodal/history-v2/generations/")) return;
    if (url.endsWith("/resume")) posts.resume.push({ url, body: r.postData() });
    else if (url.endsWith("/original/retry")) posts.retry.push(url);
    else if (url.endsWith("/original")) posts.original.push(url);
  });
  return posts;
}

test.describe("Phase F6 — Single Resume (fake backend)", () => {

  test("R1. interrupted Single shows Resume; click = exactly one bodyless POST; durable refresh drives state", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackGenerationsPosts(page);
    try {
      await seedF6(fx);

      // Enable the Interrupted status toggle so the card is reachable.
      await fx.gotoPage("history");
      const chip = page.locator('.comfymodal-studio-history-v2-chip.status-interrupted').first();
      if (!(await chip.isVisible().catch(() => false))) {
        // Open the status filter and enable Interrupted.
        const btn = page.locator('button', { hasText: "Status" }).first();
        if (await btn.count()) {
          await btn.click();
          await page.locator('input[value="interrupted"], button:has-text("Interrupted")').first().click();
        }
      }

      const overlay = await openGeneration(page, IDS.resumePreview);
      const resumeBtn = overlay.getByTestId("history-v2-resume-run");
      await expect(resumeBtn).toHaveText("Resume");
      await expect(resumeBtn).toBeEnabled();

      // No request fires before the explicit click.
      expect(posts.resume).toHaveLength(0);
      expect(posts.original).toHaveLength(0);
      expect(posts.retry).toHaveLength(0);

      await resumeBtn.click();

      // Exactly ONE bodyless POST to the frozen route.
      await expect.poll(() => posts.resume.length, { timeout: 10000 }).toBe(1);
      expect(posts.resume[0].url).toContain(`/generations/${IDS.resumePreview}/resume`);
      expect(posts.resume[0].body).toBe(null);
      expect(posts.original).toHaveLength(0);
      expect(posts.retry).toHaveLength(0);

      // Durable backend truth: SAME Generation gains ONE queued attempt with
      // the frozen preview mode preserved; the interrupted attempt retained.
      await expect.poll(async () => {
        const item = await getDetailItem(page, fx, IDS.resumePreview);
        return item.attempts.length;
      }, { timeout: 15000 }).toBe(2);
      const item = await getDetailItem(page, fx, IDS.resumePreview);
      expect(item.attempts[0]).toMatchObject({ mode: "preview", status: "interrupted" });
      expect(item.attempts[1]).toMatchObject({ mode: "preview", status: "queued" });

      // The UI renders the returned attempt via polling — no local flip.
      await expect(overlay.locator(".comfymodal-studio-history-v2-attempt")).toHaveCount(2, { timeout: 20000 });

      // Lazy progression reaches terminal completed; polling stops there.
      await expect.poll(async () => {
        const done = await getDetailItem(page, fx, IDS.resumePreview);
        return done.attempts[1].status;
      }, { timeout: 20000 }).toBe("completed");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("R2. Preview-interrupted Resume keeps Preview semantics: zero /original traffic, Preview asset untouched", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackGenerationsPosts(page);
    try {
      await seedF6(fx);
      await fx.gotoPage("history");
      const overlay = await openGeneration(page, IDS.resumePreview);
      await overlay.getByTestId("history-v2-resume-run").click();

      await expect.poll(() => posts.resume.length, { timeout: 10000 }).toBe(1);
      // Resume of a Preview run must NEVER generate an Original.
      expect(posts.original).toHaveLength(0);
      expect(posts.retry).toHaveLength(0);

      // The resumed run completes as a PREVIEW: no Original asset invented.
      await expect.poll(async () => {
        const item = await getDetailItem(page, fx, IDS.resumePreview);
        return item.attempts[1].status;
      }, { timeout: 20000 }).toBe("completed");
      const done = await getDetailItem(page, fx, IDS.resumePreview);
      expect(done.outputs[0].original_url).toBe("");
      expect(done.outputs[0].preview_url).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      expect(posts.original).toHaveLength(0);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("R3. failed / canceled / completed generations never show Resume", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedF6(fx);
      await fx.gotoPage("history");

      // Plain failed run → Retry control, not Resume (failed hidden by default).
      await enableStatus(page, "Failed");
      const failedOverlay = await openGeneration(page, IDS.retryRun);
      await expect(failedOverlay.getByTestId("history-v2-resume-run")).toHaveCount(0);
      await expect(failedOverlay.getByTestId("history-v2-retry-original")).toBeVisible();
      await failedOverlay.locator(".comfymodal-studio-history-v2-overlay-close").click();

      // Canceled → no Resume (canceled hidden by default).
      await enableStatus(page, "Canceled");
      const canceledOverlay = await openGeneration(page, IDS.canceled);
      await expect(canceledOverlay.getByTestId("history-v2-resume-run")).toHaveCount(0);
      await canceledOverlay.locator(".comfymodal-studio-history-v2-overlay-close").click();

      // Completed → Generate Again path, no Resume.
      const completedOverlay = await openGeneration(page, IDS.completed);
      await expect(completedOverlay.getByTestId("history-v2-resume-run")).toHaveCount(0);
      await expect(completedOverlay.getByTestId("history-v2-generate-again")).toBeVisible();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("R4. replay-incapable interrupted runs disable Resume BEFORE any click (irreproducible + replay_capable:false)", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackGenerationsPosts(page);
    try {
      await seedF6(fx);
      await fx.gotoPage("history");

      // Explicit irreproducible snapshot.
      const blocked = await openGeneration(page, IDS.blockedIrreproducible);
      const blockedBtn = blocked.getByTestId("history-v2-resume-run");
      await expect(blockedBtn).toBeDisabled();
      await expect(blockedBtn).toHaveText("Resume unavailable");
      await expect(blocked.locator('[data-testid="history-v2-generate-note"]'))
        .toContainText("immutable execution data");
      await blocked.locator(".comfymodal-studio-history-v2-overlay-close").click();

      // F5 projection present AND false — same truthful disabled treatment.
      const replayFalse = await openGeneration(page, IDS.replayFalse);
      const rfBtn = replayFalse.getByTestId("history-v2-resume-run");
      await expect(rfBtn).toBeDisabled();
      await expect(rfBtn).toHaveText("Resume unavailable");

      // Zero resume POSTs were possible.
      expect(posts.resume).toHaveLength(0);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("R5. refused/network-failed Resume recovers the control without converting into Retry", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackGenerationsPosts(page);
    try {
      await seedF6(fx);
      await fx.gotoPage("history");

      // One-shot network failure on the resume route.
      let failNext = true;
      await page.route("**/history-v2/generations/*/resume", async (route) => {
        if (failNext) {
          failNext = false;
          await route.abort("connectionrefused");
          return;
        }
        await route.continue();
      });

      const overlay = await openGeneration(page, IDS.resumePreview);
      const resumeBtn = overlay.getByTestId("history-v2-resume-run");
      await expect(resumeBtn).toBeEnabled();
      await resumeBtn.click();

      // Truthful failure note; the button recovers as Resume (never Retry).
      await expect(overlay.locator('[data-testid="history-v2-generate-note"]'))
        .toContainText("Resume failed", { timeout: 10000 });
      await expect(resumeBtn).toBeEnabled();
      await expect(resumeBtn).toHaveText("Resume");
      await expect(overlay.getByTestId("history-v2-retry-original")).toHaveCount(0);
      expect(posts.retry).toHaveLength(0);

      // Retry after recovery succeeds end-to-end.
      await resumeBtn.click();
      await expect.poll(() => posts.resume.length, { timeout: 10000 }).toBe(2);
      await expect.poll(async () => {
        const item = await getDetailItem(page, fx, IDS.resumePreview);
        return item.attempts.length;
      }, { timeout: 15000 }).toBe(2);
      fx.assertNoConsoleErrors(["Failed to load resource"]);
    } finally {
      fx.guard.dispose();
    }
  });
});

test.describe("Phase F6 — truthful Retry naming (fake backend)", () => {

  test("N1. plain failed ordinary Single says 'Retry run' and still POSTs only /original/retry", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const posts = trackGenerationsPosts(page);
    try {
      await seedF6(fx);
      await fx.gotoPage("history");

      // Plain failed run → Retry control, not Resume (failed hidden by default).
      await enableStatus(page, "Failed");
      const overlay = await openGeneration(page, IDS.retryRun);

      const retryBtn = overlay.getByTestId("history-v2-retry-original");
      await expect(retryBtn).toHaveText("Retry run");
      await expect(retryBtn).toBeEnabled();

      // Rendering a failed run fires nothing.
      expect(posts.retry).toHaveLength(0);
      expect(posts.original).toHaveLength(0);
      expect(posts.resume).toHaveLength(0);

      await retryBtn.click();
      await expect.poll(() => posts.retry.length, { timeout: 10000 }).toBe(1);
      expect(posts.retry[0]).toContain(`/generations/${IDS.retryRun}/original/retry`);
      expect(posts.original).toHaveLength(0);

      // Same-Generation append-only retry: failed attempt retained, new one queued.
      await expect.poll(async () => {
        const item = await getDetailItem(page, fx, IDS.retryRun);
        return item.attempts.length;
      }, { timeout: 15000 }).toBe(2);
      const item = await getDetailItem(page, fx, IDS.retryRun);
      expect(item.attempts[0]).toMatchObject({ mode: "original", status: "failed" });
      expect(item.attempts[1].mode).toBe("original");
      expect(item.attempts[1].run_id).not.toBe(item.attempts[0].run_id);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("N2. derivative Original failure keeps 'Retry Original'; Generate Again and Generate Original unchanged", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedOriginalSeed(fx);
      await fx.gotoPage("history");

      // Preview succeeded then Generate Original failed → Retry Original.
      const failedOrigOverlay = await openGeneration(page, "gen_orig_failed_original");
      await expect(failedOrigOverlay.getByTestId("history-v2-retry-original"))
        .toHaveText("Retry Original");
      await failedOrigOverlay.locator(".comfymodal-studio-history-v2-overlay-close").click();

      // Successful Original → Generate Again unchanged.
      const successOverlay = await openGeneration(page, "gen_orig_success_original");
      await expect(successOverlay.getByTestId("history-v2-generate-again")).toHaveText("Generate Again");
      await successOverlay.locator(".comfymodal-studio-history-v2-overlay-close").click();

      // Preview-only success → Generate Original unchanged.
      const previewOverlay = await openGeneration(page, "gen_orig_preview_only");
      await expect(previewOverlay.getByTestId("history-v2-generate-original")).toHaveText("Generate Original");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  async function seedOriginalSeed(fx) {
    const seeded = await fx.seedHistory("history_v2_phase_e_original");
    expect(seeded).toMatchObject({ status: "ok", v2: true });
    await fx.reload();
  }
});
